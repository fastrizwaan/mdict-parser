#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
mdx2xdxf — Convert MDict MDX/MDD files to XDXF format.

Produces:
  <name>-xdxf.zip — dictionary text and resource archive

Usage:
  python mdx2xdxf.py input.mdx [-o output_dir] [-e encoding] [-n N]
"""

import sys
import os
import re
import glob
import html
import argparse
import zipfile
from html.parser import HTMLParser

# Ensure the mdict-parser modules are importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from readmdict import MDX, MDD, _maybe_better_title


# ---------------------------------------------------------------------------
# XDXF text escaping
# ---------------------------------------------------------------------------

def xml_escape(text):
    """Escape XML special characters in literal text."""
    return html.escape(text, quote=False)


# ---------------------------------------------------------------------------
# HTML → XDXF converter (streaming parser, no dependencies)
# ---------------------------------------------------------------------------

# Block-level HTML elements that should produce line breaks in XDXF
_BLOCK_TAGS = frozenset({
    'p', 'div', 'section', 'article', 'aside', 'header', 'footer', 'nav',
    'blockquote', 'pre', 'figure', 'figcaption', 'details', 'summary',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'ul', 'ol', 'li', 'dl', 'dt', 'dd',
    'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'caption',
})

# Void (self-closing) HTML tags — never pushed onto the stack
_VOID_TAGS = frozenset({
    'br', 'hr', 'img', 'input', 'meta', 'link', 'col', 'wbr',
    'area', 'base', 'embed', 'param', 'source', 'track',
})


class HTML2XDXFParser(HTMLParser):
    """
    Convert an HTML fragment (as found in MDX entries) to XDXF markup.
    """

    # Tags with direct equivalents in basic XDXF or generally accepted visual formatting
    SIMPLE_TAG_MAP = {
        'b': 'b', 'strong': 'b',
        'i': 'i', 'em': 'i',
        'u': 'u',
        'sup': 'sup',
        'sub': 'sub',
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._pieces = []
        self._tag_stack = []

    # -- helpers --
    def _emit(self, text):
        self._pieces.append(text)

    def _emit_break(self):
        """Emit an XDXF line break."""
        self._pieces.append('<br/>')

    def _get_style_color(self, style):
        """Extract color value from a CSS style string."""
        if not style:
            return None
        m = re.search(r'color\s*:\s*([^;"\s]+)', style, re.IGNORECASE)
        return m.group(1) if m else None

    def _is_block_display(self, style):
        """Check if a CSS style string requests block-level display."""
        if not style:
            return False
        return bool(re.search(r'display\s*:\s*block', style, re.IGNORECASE))

    # -- HTMLParser callbacks --
    def handle_starttag(self, tag, attrs):
        tag_lower = tag.lower()
        attrs_dict = dict(attrs)
        style = attrs_dict.get('style', '')
        cls = attrs_dict.get('class', '')

        xdxf_tags = []

        # Special handling for known MDX layout classes
        if tag_lower == 'div':
            if cls == 'p1':
                self._emit('<b>')
                xdxf_tags.append('b')
                self._tag_stack.append((tag_lower, xdxf_tags))
                return

            if cls == 'p2p3':
                self._tag_stack.append((tag_lower, xdxf_tags))
                return

            if cls == 'p4':
                xdxf_tags.append('__block__')
                self._tag_stack.append((tag_lower, xdxf_tags))
                return

            if cls == 'p9':
                self._emit('<br/>')
                self._emit('<c c="gray">')
                xdxf_tags.append('c')
                self._tag_stack.append((tag_lower, xdxf_tags))
                return

            # fallback
            self._emit_break()
            xdxf_tags.append('__block__')
            self._tag_stack.append((tag_lower, xdxf_tags))
            return

        # <br> → <br/>
        if tag_lower == 'br':
            self._emit_break()
            return

        # <hr> → visual separator
        if tag_lower == 'hr':
            self._emit('\n<br/>─────<br/>\n')
            return

        # <img> — void tag -> rref in XDXF strict for local files
        if tag_lower == 'img':
            src = attrs_dict.get('src', '')
            if src:
                self._emit(f'<rref lctn="{xml_escape(src)}"/>')
            return

        # Other void elements: never push to stack
        if tag_lower in _VOID_TAGS:
            return

        style_color = self._get_style_color(style)
        if style_color:
            self._emit(f'<c c="{xml_escape(style_color)}">')
            xdxf_tags.append('c')

        # Simple mapped tags
        if tag_lower in self.SIMPLE_TAG_MAP:
            xdxf_tag = self.SIMPLE_TAG_MAP[tag_lower]
            self._emit(f'<{xdxf_tag}>')
            xdxf_tags.append(xdxf_tag)
            self._tag_stack.append((tag_lower, xdxf_tags))
            return

        # <a> — links
        if tag_lower == 'a':
            href = attrs_dict.get('href', '')
            if href.lower().startswith('sound://'):
                fname = href[len('sound://'):]
                self._emit(f'<rref lctn="{xml_escape(fname)}"/>')
            elif href.lower().startswith('entry://'):
                word = href[len('entry://'):]
                try:
                    from urllib.parse import unquote
                    word = unquote(word)
                except Exception:
                    pass
                self._emit(f'<kref>{xml_escape(word)}</kref>')
            
            self._tag_stack.append((tag_lower, xdxf_tags))
            return

        # <font color="...">
        if tag_lower == 'font':
            color = attrs_dict.get('color', '') or attrs_dict.get('COLOR', '')
            if color:
                self._emit(f'<c c="{xml_escape(color)}">')
                xdxf_tags.append('c')
            self._tag_stack.append((tag_lower, xdxf_tags))
            return

        # <span> — display:block check
        if tag_lower == 'span':
            if cls == 'p2':
                self._emit('<b>')
                xdxf_tags.append('b')
                self._tag_stack.append((tag_lower, xdxf_tags))
                return

            if cls == 'p3':
                self._emit(' ')
                self._emit('<sup>')
                xdxf_tags.append('sup')
                self._tag_stack.append((tag_lower, xdxf_tags))
                return

            if self._is_block_display(style):
                self._emit_break()
                xdxf_tags.append('__block__')

            self._tag_stack.append((tag_lower, xdxf_tags))
            return

        # Block-level elements
        if tag_lower in _BLOCK_TAGS:
            self._emit_break()
            xdxf_tags.append('__block__')
            self._tag_stack.append((tag_lower, xdxf_tags))
            return

        # All other tags
        self._tag_stack.append((tag_lower, xdxf_tags))

    def handle_endtag(self, tag):
        tag_lower = tag.lower()
        if tag_lower in _VOID_TAGS:
            return

        # Find the tag in the stack
        idx = -1
        for i in range(len(self._tag_stack) - 1, -1, -1):
            if self._tag_stack[i][0] == tag_lower:
                idx = i
                break
        
        if idx == -1:
            return # ignore unmatched end tag

        # Pop everything up to the found tag
        while len(self._tag_stack) > idx:
            popped_html, xdxf_tags = self._tag_stack.pop()
            for x_tag in reversed(xdxf_tags):
                if x_tag and x_tag not in ('__block__', '__skip__'):
                    self._emit(f'</{x_tag}>')
                    if tag_lower == 'span' and x_tag == 'sup':
                        self._emit_break()

    def handle_data(self, data):
        if self._tag_stack:
            # Check if we are skipping content
            # (only if __skip__ is in the current tag's xdxf_tags)
            if any('__skip__' in x_tags for _, x_tags in self._tag_stack):
                return
        self._emit(xml_escape(data))

    def handle_entityref(self, name):
        ch = html.unescape(f'&{name};')
        self._emit(xml_escape(ch))

    def handle_charref(self, name):
        ch = html.unescape(f'&#{name};')
        self._emit(xml_escape(ch))

    def get_result(self):
        # Clean up any remaining unclosed tags
        while self._tag_stack:
            popped_html, xdxf_tags = self._tag_stack.pop()
            for x_tag in reversed(xdxf_tags):
                if x_tag and x_tag not in ('__block__', '__skip__'):
                    self._emit(f'</{x_tag}>')

        res = ''.join(self._pieces)
        res = res.replace('\n', '')
        # Tighten <br/> collapsing
        res = re.sub(r'(?:\s*<br/>\s*)+', '<br/>', res)
        # Remove leading/trailing <br/>
        res = re.sub(r'^<br/>\n?', '', res)
        res = re.sub(r'<br/>\n?$', '', res)
        return res.strip()


def html_to_xdxf(html_text):
    """Convert an HTML string (from MDX) to XDXF markup."""
    if not html_text:
        return ''

    link_match = re.match(r'^@@@LINK=(.+)', html_text, re.IGNORECASE)
    if link_match:
        target = link_match.group(1).strip()
        return f'<kref>{xml_escape(target)}</kref>'

    parser = HTML2XDXFParser()
    try:
        parser.feed(html_text)
    except Exception:
        return xml_escape(html_text)
    return parser.get_result()


# ---------------------------------------------------------------------------
# XDXF file writer
# ---------------------------------------------------------------------------

def format_xdxf_entry(headword, body_xdxf):
    """
    Format a single XDXF entry strictly following xdxf_strict.dtd.
    """
    lines = []
    lines.append('    <ar>')
    lines.append(f'      <k>{xml_escape(headword)}</k>')
    
    body_xdxf_stripped = body_xdxf.strip()
    if body_xdxf_stripped:
        lines.append('      <def>')
        lines.append('        <deftext>')
        # Indent the body slightly for readability in the XML file
        for line in body_xdxf.split('\n'):
            if line.strip():
                lines.append('          ' + line.rstrip())
            else:
                lines.append('')
        lines.append('        </deftext>')
        lines.append('      </def>')
        
    lines.append('    </ar>')
    
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Main conversion logic
# ---------------------------------------------------------------------------

def find_mdd_files(mdx_path):
    """
    Find companion MDD files for an MDX file.
    Looks for: base.mdd, base.1.mdd, base.2.mdd, ...
    """
    base = os.path.splitext(mdx_path)[0]
    mdd_files = []

    # Primary .mdd
    primary = base + '.mdd'
    if os.path.exists(primary):
        mdd_files.append(primary)

    # Numbered .N.mdd
    for path in sorted(glob.glob(base + '.*.mdd')):
        if path not in mdd_files:
            mdd_files.append(path)

    return mdd_files


def extract_dict_name(mdx):
    """Extract dictionary name from MDX header."""
    header = mdx.header
    # Same logic as readmdict.py / mdx2dsl.py: skip placeholder Title, use Description line
    raw = _maybe_better_title(header)
    if isinstance(raw, bytes):
        val = raw.decode('utf-8', errors='replace')
    else:
        val = str(raw)
    val = re.sub(r'<[^>]+>', '', val).strip()
    if val:
        return val
    for key in (b'Title', b'title', b'Description', b'description'):
        if key in header:
            v = header[key]
            if isinstance(v, bytes):
                v = v.decode('utf-8', errors='replace')
            v = re.sub(r'<[^>]+>', '', v).strip()
            if v:
                return v[:200] if key.lower() == b'description' else v
    return None


def extract_language(mdx, key_names):
    """Try to extract a language string from MDX header."""
    header = mdx.header
    for key in key_names:
        if key in header:
            val = header[key]
            if isinstance(val, bytes):
                val = val.decode('utf-8', errors='replace')
            val = val.strip()
            if val:
                return val
    return None


def convert_mdx_to_xdxf(mdx_path, output_dir=None, encoding='', passcode=None,
                        max_entries=0, keep_xdxf=False, no_zip=False):
    """
    Convert an MDX file (and companion MDDs) to XDXF format.

    Args:
        mdx_path:    Path to the .mdx file
        output_dir:  Directory for output files (default: same as input)
        encoding:    Override encoding (default: auto-detect from header)
        passcode:    Passcode tuple (regcode, userid) for encrypted files
        max_entries: Limit number of entries (0 = unlimited, useful for testing)
        keep_xdxf:   Keep the .xdxf file after zipping
        no_zip:      Do not create the zip file

    Returns:
        Tuple of (xdxf_path, zip_path_or_None)
    """
    mdx_path = os.path.abspath(mdx_path)
    base_name = os.path.splitext(os.path.basename(mdx_path))[0]

    if output_dir is None:
        output_dir = os.path.dirname(mdx_path)
    os.makedirs(output_dir, exist_ok=True)

    xdxf_path = os.path.join(output_dir, base_name + '.xdxf')
    zip_path = os.path.join(output_dir, base_name + '-xdxf.zip')

    # ---- Phase 1: Read MDX and write XDXF ----
    print(f'Reading MDX: {mdx_path}', file=sys.stderr)
    mdx = MDX(mdx_path, encoding=encoding, substyle=True, passcode=passcode)

    num_entries = len(mdx)
    print(f'  Entries: {num_entries}', file=sys.stderr)

    # Extract metadata
    dict_name = extract_dict_name(mdx) or base_name
    idx_lang = extract_language(mdx, [b'SourceLanguage', b'From']) or 'ENG'
    cnt_lang = extract_language(mdx, [b'TargetLanguage', b'To']) or idx_lang
    
    idx_lang = re.sub(r'\W+', '', idx_lang) or 'ENG'
    cnt_lang = re.sub(r'\W+', '', cnt_lang) or 'ENG'

    # Print header info
    print(f'  Name: {dict_name}', file=sys.stderr)
    print(f'  Languages: {idx_lang} \u2192 {cnt_lang}', file=sys.stderr)

    import datetime
    now = datetime.datetime.now()
    date_str = now.strftime('%d-%m-%Y')

    # Write XDXF as UTF-8
    print(f'Writing XDXF: {xdxf_path}', file=sys.stderr)
    with open(xdxf_path, 'w', encoding='utf-8') as f:
        def write_line(text):
            f.write(text + '\n')

        # XDXF headers
        write_line('<?xml version="1.0" encoding="UTF-8" ?>')
        write_line('<!DOCTYPE xdxf SYSTEM "xdxf_strict.dtd">')
        write_line('<xdxf revision="034">')
        write_line('  <meta_info>')
        write_line('    <languages>')
        write_line(f'      <from xml:lang="{xml_escape(idx_lang)}"/>')
        write_line(f'      <to xml:lang="{xml_escape(cnt_lang)}"/>')
        write_line('    </languages>')
        write_line(f'    <title>{xml_escape(dict_name)}</title>')
        write_line('    <description>Converted from MDX</description>')
        write_line('    <file_ver>1.0</file_ver>')
        write_line(f'    <creation_date>{date_str}</creation_date>')
        write_line(f'    <last_edited_date>{date_str}</last_edited_date>')
        write_line('  </meta_info>')
        write_line('  <lexicon>')
        write_line('')

        count = 0
        skipped = 0
        first_skip_err = None
        for key_bytes, value_bytes in mdx.items():
            # Decode key
            try:
                if isinstance(key_bytes, bytes):
                    key = key_bytes.decode('utf-8', errors='replace')
                else:
                    key = str(key_bytes)
                key = key.strip()

                if not key:
                    skipped += 1
                    continue

                # Decode value
                if isinstance(value_bytes, bytes):
                    value = value_bytes.decode('utf-8', errors='replace')
                else:
                    value = str(value_bytes)
                value = value.strip()

                # Convert HTML to XDXF
                body_xdxf = html_to_xdxf(value)

                # Format entry
                entry_text = format_xdxf_entry(key, body_xdxf)
                
                f.write(entry_text + '\n\n')

                count += 1
                if count % 1000 == 0:
                    print(f'  Processed {count}/{num_entries} entries...', file=sys.stderr)

                if max_entries and count >= max_entries:
                    print(f'  Stopped at {max_entries} entries (--max-entries limit)',
                          file=sys.stderr)
                    break
            except Exception as e:
                skipped += 1
                if first_skip_err is None:
                    first_skip_err = e

        write_line('  </lexicon>')
        write_line('</xdxf>')

    print(f'  Wrote {count} entries ({skipped} skipped)', file=sys.stderr, flush=True)
    if skipped and first_skip_err is not None:
        print(
            f'  WARNING: first conversion error was: {first_skip_err!r}',
            file=sys.stderr,
            flush=True,
        )

    if not no_zip:
        print(f'Creating zip distribution: {zip_path}', file=sys.stderr)
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
            # Add the XDXF file first
            print(f'  Adding: {os.path.basename(xdxf_path)}', file=sys.stderr)
            zf.write(xdxf_path, arcname=os.path.basename(xdxf_path))
    
            # ---- Phase 2: Pack MDD resources into zip ----
            mdd_files = find_mdd_files(mdx_path)
            if mdd_files:
                print(f'Found {len(mdd_files)} MDD file(s):', file=sys.stderr)
                for mf in mdd_files:
                    print(f'  {mf}', file=sys.stderr)
    
                res_count = 0
                for mdd_path in mdd_files:
                    print(f'  Reading: {os.path.basename(mdd_path)}', file=sys.stderr)
                    try:
                        mdd = MDD(mdd_path, passcode=passcode)
                    except Exception as e:
                        print(f'  WARNING: Failed to read {mdd_path}: {e}', file=sys.stderr)
                        continue
    
                    for fname_bytes, data in mdd.items():
                        if isinstance(fname_bytes, bytes):
                            fname = fname_bytes.decode('utf-8', errors='replace')
                        else:
                            fname = str(fname_bytes)
    
                        # Normalize path: \ → /, strip leading /
                        fname = fname.replace('\\', '/')
                        fname = fname.lstrip('/')
    
                        try:
                            zf.writestr(fname, data)
                            res_count += 1
                        except Exception as e:
                            print(f'  WARNING: Failed to add {fname}: {e}', file=sys.stderr)
    
                        if res_count % 5000 == 0:
                            print(f'  Packed {res_count} resources...', file=sys.stderr)
    
                print(f'  Packed {res_count} resources total', file=sys.stderr)
            else:
                print('No MDD files found, zip will only contain XDXF', file=sys.stderr)
    else:
        print('Skipping zip creation as requested.', file=sys.stderr)
        zip_path = None

    # Clean up the standalone .xdxf file since it's now in the zip
    if not keep_xdxf and not no_zip:
        try:
            os.remove(xdxf_path)
        except OSError:
            pass

    print('Done!', file=sys.stderr)
    return xdxf_path, zip_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Convert MDict MDX/MDD files to XDXF format.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s dictionary.mdx
  %(prog)s dictionary.mdx -o /output/dir
  %(prog)s dictionary.mdx --max-entries 100   # quick test
""")

    parser.add_argument('input', help='Path to the .mdx file')
    parser.add_argument('-o', '--output-dir', default=None,
                        help='Output directory (default: same as input)')
    parser.add_argument('-e', '--encoding', default='',
                        help='Override encoding (default: auto-detect)')
    parser.add_argument('-n', '--max-entries', type=int, default=0,
                        help='Maximum entries to convert (0 = all)')
    parser.add_argument('-p', '--passcode', default=None,
                        help='Passcode as regcode,userid for encrypted files')
    parser.add_argument('-k', '--keep', action='store_true',
                        help='Keep the uncompressed .xdxf file after zipping')
    parser.add_argument('--no-zip', action='store_true',
                        help='Do not create a zip file, only output the .xdxf file')

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f'Error: file not found: {args.input}', file=sys.stderr)
        sys.exit(1)

    passcode = None
    if args.passcode:
        import codecs
        try:
            regcode, userid = args.passcode.split(',')
            regcode = codecs.decode(regcode, 'hex')
            passcode = (regcode, userid)
        except Exception:
            print('Error: passcode must be regcode,userid (hex,string)',
                  file=sys.stderr)
            sys.exit(1)

    xdxf_path, zip_path = convert_mdx_to_xdxf(
        args.input,
        output_dir=args.output_dir,
        encoding=args.encoding,
        passcode=passcode,
        max_entries=args.max_entries,
        keep_xdxf=args.keep,
        no_zip=args.no_zip,
    )

    print(f'\nOutput:', file=sys.stderr)
    if zip_path:
        print(f'  Zip: {zip_path}', file=sys.stderr)
    if args.keep or args.no_zip:
        print(f'  XDXF: {xdxf_path}', file=sys.stderr)


if __name__ == '__main__':
    main()

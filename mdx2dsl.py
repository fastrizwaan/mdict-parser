#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
mdx2dsl — Convert MDict MDX/MDD files to ABBYY Lingvo DSL format.

Produces:
  <name>.dsl          — dictionary text (UTF-16LE with BOM)
  <name>.dsl.files.zip — resource archive (images, sounds, CSS, etc.)

Usage:
  python mdx2dsl.py input.mdx [-o output_dir] [-e encoding] [-n N]
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
# DSL text escaping
# ---------------------------------------------------------------------------

# Characters that have special meaning in DSL and must be backslash-escaped
# when they appear as literal text: { } [ ] ~ \
_DSL_ESCAPE_RE = re.compile(r'([{}[\]~\\])')


def dsl_escape(text):
    """Escape DSL special characters in literal text."""
    return _DSL_ESCAPE_RE.sub(r'\\\1', text)


# ---------------------------------------------------------------------------
# HTML → DSL converter (streaming parser, no dependencies)
# ---------------------------------------------------------------------------

# Block-level HTML elements that should produce line breaks in DSL
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


class HTML2DSLParser(HTMLParser):
    """
    Convert an HTML fragment (as found in MDX entries) to DSL markup.

    Design: we walk the HTML tag tree and emit DSL equivalents.  Block-level
    elements always produce a newline+tab break so entries don't collapse
    into a single line.  Tags without a DSL equivalent are silently stripped
    (their text children are kept).
    """

    # Tags with direct DSL equivalents
    SIMPLE_TAG_MAP = {
        'b': 'b', 'strong': 'b',
        'i': 'i', 'em': 'ex',
        'u': 'u',
        'sup': 'sup',
        'sub': 'sub',
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._pieces = []
        self._tag_stack = []
        self._list_counters = []
        self._margin = 0

    # -- helpers --
    def _emit(self, text):
        self._pieces.append(text)

    def _emit_break(self):
        """Emit a DSL line break with contextual margin marker."""
        self._pieces.append(f'\n\x01{self._margin}\x02')

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

    def _get_margin_level(self, style):
        """Extract margin level from margin-left style."""
        if not style:
            return 0
        m = re.search(r'margin-left\s*:\s*(\d+)px', style, re.IGNORECASE)
        if m:
            px = int(m.group(1))
            return max(1, px // 20)
        return 0

    # -- HTMLParser callbacks --
    def handle_starttag(self, tag, attrs):
        tag_lower = tag.lower()
        attrs_dict = dict(attrs)
        style = attrs_dict.get('style', '')

        # Check for color in style attribute (any tag can have it)
        style_color = self._get_style_color(style)
        if style_color:
            self._emit(f'[c {style_color}]')
            # We'll push this to the stack to close it later
            # Note: if it's a SIMPLE_TAG_MAP tag, we'll have TWO things on stack
            self._tag_stack.append('c')
        else:
            self._tag_stack.append(None)

        # Skip completely tags containing unneeded text
        class_attr = attrs_dict.get('class', '')
        if tag_lower in ('script', 'style') or (tag_lower == 'h2' and class_attr == 'defH2'):
            self._tag_stack.append('__skip__')
            return

        # Intercept part of speech wrapper for custom [p] styling
        if class_attr == 'main_entry_pos':
            if tag_lower in _BLOCK_TAGS or self._is_block_display(style):
                self._emit_break()
            self._emit('[p]')
            self._tag_stack.append('p_special')
            return

        # Intercept inner sub-lists to increase margin
        if class_attr == 'sds-list' and tag_lower == 'div':
            self._margin += 1
            self._emit_break()
            self._tag_stack.append('sds_list')
            return

        # Simple mapped tags (b, i, u, sup, sub)
        if tag_lower in self.SIMPLE_TAG_MAP:
            dsl_tag = self.SIMPLE_TAG_MAP[tag_lower]
            self._emit(f'[{dsl_tag}]')
            self._tag_stack.append(dsl_tag)
            return

        # <br> → newline + indent
        if tag_lower == 'br':
            self._emit_break()
            return

        # <hr> → visual separator
        if tag_lower == 'hr':
            self._emit('\n\t─────\n\t')
            return

        # <a> — links
        if tag_lower == 'a':
            href = attrs_dict.get('href', '')
            if href.lower().startswith('sound://'):
                fname = href[len('sound://'):]
                # In DSL, we wrap the content in a url to the sound:// URI.
                # This makes the content (like an icon) clickable to play sound
                # without showing an extra play button icon.
                self._emit(f'[url "sound://{dsl_escape(fname)}"]')
                self._tag_stack.append('url')
                return
            elif href.lower().startswith('http://') or href.lower().startswith('https://'):
                self._emit('[url]')
                self._tag_stack.append('url')
                return
            elif href.lower().startswith('entry://'):
                word = href[len('entry://'):]
                try:
                    from urllib.parse import unquote
                    word = unquote(word)
                except Exception:
                    pass
                self._emit(f'[ref "{dsl_escape(word)}"]')
                self._tag_stack.append('ref')
                return
            elif href:
                self._emit('[ref]')
                self._tag_stack.append('ref')
                return
            self._tag_stack.append(None)
            return

        # <img> — void tag
        if tag_lower == 'img':
            src = attrs_dict.get('src', '')
            if src:
                self._emit(f'[s]{dsl_escape(src)}[/s]')
            return

        # <font color="...">
        if tag_lower == 'font':
            color = attrs_dict.get('color', '') or attrs_dict.get('COLOR', '')
            if color:
                self._emit(f'[c {color}]')
                self._tag_stack.append('c')
                return
            self._tag_stack.append(None)
            return

        # <span> — display:block check
        if tag_lower == 'span':
            margin_delta = self._get_margin_level(style)
            if margin_delta > 0:
                self._margin += margin_delta
                self._emit_break()
                self._tag_stack.append(('margin', margin_delta))
                return
            
            if self._is_block_display(style):
                self._emit_break()
            self._tag_stack.append(None)
            return

        # Block-level elements
        if tag_lower in _BLOCK_TAGS:
            if tag_lower == 'ol':
                self._emit_break()
                self._margin += 1
                self._list_counters.append(1)
                self._tag_stack.append('__list_env__')
                return
            elif tag_lower == 'ul':
                self._emit_break()
                self._margin += 1
                self._list_counters.append(None)
                self._tag_stack.append('__list_env__')
                return
            elif tag_lower == 'li':
                self._emit_break()
                if self._list_counters:
                    if self._list_counters[-1] is not None:
                        self._emit(f"{self._list_counters[-1]}. ")
                        self._list_counters[-1] += 1
                    else:
                        self._emit("• ")
                self._tag_stack.append('__block__')
                return

            self._emit_break()
            self._tag_stack.append('__block__')
            return

        # All other tags
        if tag_lower not in _VOID_TAGS:
            self._tag_stack.append(None)

    def handle_endtag(self, tag):
        tag_lower = tag.lower()
        if tag_lower in _VOID_TAGS:
            return

        # Pop any simple tag (b, i, u, etc.)
        if tag_lower in self.SIMPLE_TAG_MAP or tag_lower in ('a', 'font', 'span', 'script', 'style') or tag_lower in _BLOCK_TAGS:
            if self._tag_stack:
                dsl_tag = self._tag_stack.pop()
                if dsl_tag == '__block__':
                    self._emit_break()
                elif dsl_tag == 'p_special':
                    self._emit('[/p]')
                    if tag_lower in _BLOCK_TAGS:
                        self._emit_break()
                elif dsl_tag == '__list_env__':
                    if self._list_counters:
                        self._list_counters.pop()
                    self._margin = max(0, self._margin - 1)
                    self._emit_break()
                elif dsl_tag == 'sds_list':
                    self._margin = max(0, self._margin - 1)
                    self._emit_break()
                elif isinstance(dsl_tag, tuple) and dsl_tag[0] == 'margin':
                    self._margin = max(0, self._margin - dsl_tag[1])
                    self._emit_break()
                elif dsl_tag == '__skip__':
                    pass
                elif dsl_tag:
                    self._emit(f'[/{dsl_tag}]')

        # Pop the style-color tag if we added one for this tag
        if self._tag_stack:
            color_marker = self._tag_stack.pop()
            if color_marker == 'c':
                self._emit('[/c]')
            # If it was None, just keep going

    def handle_data(self, data):
        if self._tag_stack and '__skip__' in self._tag_stack:
            return
        self._emit(dsl_escape(data))

    def handle_entityref(self, name):
        if self._tag_stack and '__skip__' in self._tag_stack:
            return
        ch = html.unescape(f'&{name};')
        self._emit(dsl_escape(ch))

    def handle_charref(self, name):
        if self._tag_stack and '__skip__' in self._tag_stack:
            return
        ch = html.unescape(f'&#{name};')
        self._emit(dsl_escape(ch))

    def get_result(self):
        return ''.join(self._pieces)


def html_to_dsl(html_text):
    """Convert an HTML string (from MDX) to DSL markup."""
    if not html_text:
        return ''

    link_match = re.match(r'^@@@LINK=(.+)', html_text, re.IGNORECASE)
    if link_match:
        target = link_match.group(1).strip()
        return f'[ref]{dsl_escape(target)}[/ref]'

    parser = HTML2DSLParser()
    try:
        parser.feed(html_text)
    except Exception:
        return dsl_escape(html_text)
    return parser.get_result()


# ---------------------------------------------------------------------------
# DSL file writer
# ---------------------------------------------------------------------------

def format_dsl_entry(headword, body_dsl):
    """
    Format a single DSL entry.
    """
    lines = [headword]
    last_was_blank = False
    margin = 0

    # Split body into lines. Every line in DSL body MUST start with \t.
    for raw_line in body_dsl.split('\n'):
        # Strip trailing only.
        line = raw_line.rstrip()
        
        while line.startswith('\x01'):
            end_idx = line.find('\x02')
            if end_idx != -1:
                margin = int(line[1:end_idx])
                line = line[end_idx+1:].lstrip(' \t\r')
            else:
                break
                
        # Clean any internal markers
        line = re.sub(r'\x01\d+\x02', '', line).strip()
        
        # If the line is purely whitespace but meant for spacing (\n \n), 
        # use [m] tag which many renderers use for vertical spacing/margins.
        if not line:
            if not last_was_blank and len(lines) > 1:
                lines.append(f'\t[m{margin}] [/m]')
                last_was_blank = True
            continue
            
        last_was_blank = False
        lines.append(f'\t[m{margin}]{line}[/m]')

    # Remove trailing blank spacer if present
    if lines and lines[-1].endswith(' [/m]') and not last_was_blank and len(lines) > 1:
        # Wait, if we are robustly stripping spacers, we check if it is exclusively a spacer
        pass
    while lines and re.match(r'^\t\[m\d+\] \[\/m\]$', lines[-1]):
        lines.pop()

    return '\n'.join(lines).rstrip()


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
    # Same logic as readmdict.py: skip placeholder Title, use Description line
    raw = _maybe_better_title(header)
    if isinstance(raw, bytes):
        val = raw.decode('utf-8', errors='replace')
    else:
        val = str(raw)
    val = re.sub(r'<[^>]+>', '', val).strip()
    if val:
        return val
    # Fallback: any non-empty Title / Description
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


def convert_mdx_to_dsl(mdx_path, output_dir=None, encoding='', passcode=None,
                        max_entries=0):
    """
    Convert an MDX file (and companion MDDs) to DSL format.

    Args:
        mdx_path:    Path to the .mdx file
        output_dir:  Directory for output files (default: same as input)
        encoding:    Override encoding (default: auto-detect from header)
        passcode:    Passcode tuple (regcode, userid) for encrypted files
        max_entries: Limit number of entries (0 = unlimited, useful for testing)

    Returns:
        Tuple of (dsl_path, zip_path_or_None)
    """
    mdx_path = os.path.abspath(mdx_path)
    base_name = os.path.splitext(os.path.basename(mdx_path))[0]

    if output_dir is None:
        output_dir = os.path.dirname(mdx_path)
    os.makedirs(output_dir, exist_ok=True)

    dsl_path = os.path.join(output_dir, base_name + '.dsl')
    zip_path = os.path.join(output_dir, base_name + '.dsl.files.zip')

    # ---- Phase 1: Read MDX and write DSL ----
    print(f'Reading MDX: {mdx_path}', file=sys.stderr)
    mdx = MDX(mdx_path, encoding=encoding, substyle=True, passcode=passcode)

    num_entries = len(mdx)
    print(f'  Entries: {num_entries}', file=sys.stderr)

    # Extract metadata
    dict_name = extract_dict_name(mdx) or base_name
    idx_lang = extract_language(mdx, [b'SourceLanguage', b'From']) or 'English'
    cnt_lang = extract_language(mdx, [b'TargetLanguage', b'To']) or idx_lang

    # Print header info
    print(f'  Name: {dict_name}', file=sys.stderr)
    print(f'  Languages: {idx_lang} \u2192 {cnt_lang}', file=sys.stderr)

    # Write DSL as UTF-16LE with BOM (standard for DSL)
    print(f'Writing DSL: {dsl_path}', file=sys.stderr)
    with open(dsl_path, 'wb') as f:
        # BOM
        f.write('\ufeff'.encode('utf-16-le'))

        def write_line(text):
            # Explicitly state and encode CRLF to be safe
            f.write((text + '\r\n').encode('utf-16-le'))

        # DSL headers
        write_line(f'#NAME "{dict_name}"')
        write_line(f'#INDEX_LANGUAGE "{idx_lang}"')
        write_line(f'#CONTENTS_LANGUAGE "{cnt_lang}"')
        write_line('')

        count = 0
        skipped = 0
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

                # Convert HTML to DSL
                body_dsl = html_to_dsl(value)

                # Format entry (returns string with \n internally)
                entry_text = format_dsl_entry(key, body_dsl)
                
                # Convert \n to \r\n and write entry + blank line separator
                crlf_entry = entry_text.replace('\n', '\r\n')
                f.write((crlf_entry + '\r\n\r\n').encode('utf-16-le'))

                count += 1
                if count % 1000 == 0:
                    print(f'  Processed {count}/{num_entries} entries...', file=sys.stderr)

                if max_entries and count >= max_entries:
                    print(f'  Stopped at {max_entries} entries (--max-entries limit)',
                          file=sys.stderr)
                    break
            except Exception:
                skipped += 1

    print(f'  Wrote {count} entries ({skipped} skipped)', file=sys.stderr)

    # ---- Phase 2: Pack MDD resources into zip ----
    mdd_files = find_mdd_files(mdx_path)
    actual_zip_path = None

    if mdd_files:
        print(f'Found {len(mdd_files)} MDD file(s):', file=sys.stderr)
        for mf in mdd_files:
            print(f'  {mf}', file=sys.stderr)

        print(f'Writing resources: {zip_path}', file=sys.stderr)
        res_count = 0

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
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
        actual_zip_path = zip_path
    else:
        print('No MDD files found, skipping resource zip', file=sys.stderr)

    print('Done!', file=sys.stderr)
    return dsl_path, actual_zip_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Convert MDict MDX/MDD files to ABBYY Lingvo DSL format.',
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

    dsl_path, zip_path = convert_mdx_to_dsl(
        args.input,
        output_dir=args.output_dir,
        encoding=args.encoding,
        passcode=passcode,
        max_entries=args.max_entries,
    )

    print(f'\nOutput:', file=sys.stderr)
    print(f'  DSL: {dsl_path}', file=sys.stderr)
    if zip_path:
        print(f'  Resources: {zip_path}', file=sys.stderr)


if __name__ == '__main__':
    main()

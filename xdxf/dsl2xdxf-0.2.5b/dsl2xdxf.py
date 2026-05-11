#!/usr/bin/env python
"""*************************************************************************
 *   Copyright (C) 2005 by Alexander Goryachev                             *
 *   thorn_st@users.sourceforge.net                                        *
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 *   This program is distributed in the hope that it will be useful,       *
 *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
 *   GNU General Public License for more details.                          *
 *                                                                         *
 *   You should have received a copy of the GNU General Public License     *
 *   along with this program; if not, write to the                         *
 *   Free Software Foundation, Inc.,                                       *
 *   59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.             *
  ***************************************************************************"""

import sys, re, string, getopt, os, site, codecs, tempfile, shutil, zipfile, gzip
from locale import getdefaultlocale
from stat import *

Version = '0.2.5b'

ProgramName = os.path.basename(sys.argv[0])

FromLanguage = ToLanguage = Name = AbbrevFile = ''
NL = '' #new line simbol
TB = '' #tab simbol

Encodings = { #encodings supported by Lingvo v.8 (apart from unicode)
    'latin':'CP1252',
    'cyrillic':'CP1251', #default if not unicode, and there's no #SOURCE_CODE_PAGE tag
    'easterneuropean':'CP1250'}

LongLanguages = { #languages supported by Lingvo v.8
    'afrikaans':'Afrikaans',
    'basque':'Basque',
    'belarusian':'Belarusian',
    'bulgarian':'Bulgarian',
    'czech':'Czech',
    'danish':'Danish',
    'dutch':'Dutch',
    'english':'English',
    'finnish':'Finnish',
    'french':'French',
    'german':'German',
    'germannewspelling':'German',
    'hungarian':'Hungarian',
    'indonesian':'Indonesian',
    'italian':'Italian',
    'norwegianbokmal':'Norwegian',
    'norwegiannynorsk':'Norwegian',
    'polish':'Polish',
    'portuguesestandard':'Portuguese',
    'russian':'Russian',
    'serbiancyrillic':'Serbian',
    'spanishmodernsort':'Spanish',
    'spanishtraditionalsort':'Spanish',
    'swahili':'Swahili',
    'swedish':'Swedish',
    'ukrainian':'Ukrainian'}

ShortLanguages = { #short versions of language names
    'afrikaans':'afr',
    'basque':'baq',
    'belarusian':'bel',
    'bulgarian':'bul',
    'czech':'cze',
    'danish':'dan',
    'dutch':'dut',
    'english':'eng',
    'finnish':'fin',
    'french':'fra',
    'german':'ger',
    'germannewspelling':'ger',
    'hungarian':'hun',
    'indonesian':'ind',
    'italian':'ita',
    'norwegianbokmal':'nob',
    'norwegiannynorsk':'nno',
    'polish':'pol',
    'portuguesestandard':'por',
    'russian':'rus',
    'serbiancyrillic':'scc',
    'spanishmodernsort':'spa',
    'spanishtraditionalsort':'spa',
    'swahili':'swa',
    'swedish':'swe',
    'ukrainian':'ukr'}

SF = r'(?<![\\])' #backslash filter
Tags = { #key:replacement ('old tag':'new tag')
    '[b]':'<b>','[/b]':'</b>',                          #bold
    '[i]':'<i>','[/i]':'</i>',                          #italic
    '[u]':'<u>','[/u]':'</u>',                          #underline
    '[*]':'','[/*]':'',                                 #secondary representation
    '[trn]':'<dtrn>','[/trn]':'</dtrn>',                #translate zone (direct meaning)
    '[t]':'<tr>','[/t]':'</tr>',                        #transcription
    '[c]':'<c>','[/c]':'</c>',                          #coloured text
    '[m]':'',
    '[/m]':'',                                          #end of indentation
    '[ex]':'<ex><ex_orig>','[/ex]':'</ex_orig></ex>',   #example
    '[ref]':'<kref>','[/ref]':'</kref>',                #reference to an another article
    '[!trs]':'','[/!trs]':'',                           #exclude from indexation
    '[/lang]':'',                                       #end of language code, if it different from translate language
    '[p]':'<abbr>','[/p]':'</abbr>',                    #show abbreviation
    '[sub]':'<sub>','[/sub]':'</sub>',                  #low index
    '[sup]':'<sup>','[/sup]':'</sup>',                  #high index
    '[com]':'<co>','[/com]':'</co>',                    #comments zone
    '{{':'<!--','}}':'-->',                             #absolutely ignored comments
    '<':'&lt;','>':'&gt;',
    '&':'&amp;',
    '"':'&quot;',
	'\r\n':'<br/>\n',
	'\n':'<br/>\n'}

TagsPattern = r'\s+(?:\[\*\])*@\s*.*|\s+(?:\[/\*\])*@\s*$|\[b\]|\[/b\]|\[i\]|\[/i\]|\[u\]|\[/u\]|\[\*\]|\[/\*\]|\[trn\]'+\
    r'|\[/trn\]|\[t\]|\[/t\]|\[c\s+[a-zA-Z0-9#]+\s*\]|\[c\]|\[/c\]|\[m\]|\[m\d\]|\[/m\]|\[ex\]'+\
    r'|\[/ex\]|\[!trs\]|\[/!trs\]|'+SF+r'<<.*?'+SF+r'>>|\[\s*lang\s+id\s*\=\s*\d\s*\]'+\
    r'|\[/lang\]|\[p\]|\[/p\]|\[sub\]|\[/sub\]|\[sup\]|\[/sup\]|\[com\]'+\
    r'|\[/com\]|\[ref\]|\[/ref\]|\{\{|\}\}|'+SF+r'\^'+SF+r'~|'+SF+r'~|<|>|\[s\].+?\[/s\]|\[url\].+?\[/url\]|&|"|\r\n|\n'

XMLHeaderData = {  #Copirights, descriptions, versions and other stuff
    'type'                      : '',
    'lang_from'                 : '',
    'lang_to'                   : '',
    'description'               : '',
    'full_name'					: ''}

KeepXDXF = False
NoZip = False

def perror ( *message ) :
    """
    Prints messages to stderr.
    Accepts variable number of arguments.
    """
    for a in message : print(a, end=' ', file=sys.stderr)

def terminate ( *msg ) :
    """
    Terminate the program with post mortem message.
    """
    perror('Error: ', *msg)
    sys.exit(1)


def ParseDSLHeader(DSLFileDesc, UTF) :
	"""DSLFileDesc - input file descriptor,
	UTF - input file encoding

	Return: Contents of the #SOURCE_CODE_PAGE tag (if found) or ''.
	"""
	global Name, FromLanguage, ToLanguage

	DSLSourceCodePage = ''

	while True :
		pos = DSLFileDesc.tell()
		strng = DSLFileDesc.readline()
		if not strng :
			DSLFileDesc.close()
			break
		if isinstance(strng, bytes):
			strng = strng.decode('latin-1')

		cd = re.search(r'#NAME(?:\s+)\"(.+)\"',strng)
		if cd :
			if not Name :
				#print('Found tag "#NAME" - dictionary name: "'+cd.group(1)+'"')
				Name = cd.group(1)
			continue

		try :
			cd = re.search(r'#INDEX_LANGUAGE(?:\s+)\"([a-zA-Z]+)\"',strng)
			if cd :
				if not FromLanguage :
					#print('Found tag "#INDEX_LANGUAGE" - original language: "'+cd.group(1)+'"')
					FromLanguage = cd.group(1).lower()
				continue

			cd = re.search(r'#CONTENTS_LANGUAGE(?:\s+)\"([a-zA-Z]+)\"',strng)
			if cd :
				if not ToLanguage :
					#print('Found tag "#CONTENTS_LANGUAGE" - target language: "'+cd.group(1)+'"')
					ToLanguage = cd.group(1).lower()
				continue

			cd = re.search(r'#SOURCE_CODE_PAGE(?:\s+)\"([a-zA-Z]+)\"',strng)
			if cd :
				if not UTF : #if file is in unicode - ignore tag #SOURCE_CODE_PAGE
					#print('Found tag "#SOURCE_CODE_PAGE" - source code page: "'+cd.group(1)+'"')
					try :
						DSLSourceCodePage = Encodings[cd.group(1).lower()]
					except KeyError : terminate('Unsupported code page: "'+cd.group(1)+'", save input file in Unicode.\n')
				continue
		except KeyError : terminate('Unknown tag value "'+cd.group(1)+'"')

#    if not strng[:1].isspace(): MainBuffer.insert(0,strng);break
		if not strng[:1].isspace(): DSLFileDesc.seek(pos);break
	return DSLSourceCodePage
#--------------------- end of DSL header


def RecodeToUTF8(Path, FileType) :
	"""Recodes file from utf16 to utf8,
	saves to a temporal file, and returns descriptor to it.
	FileType - 'dsl' or 'abr' or 'ann'"""

	try:

		print('Recoding "'+FileType+'" file to UTF-8')

		Encoding = 'CP1251'
		FileLength = os.stat(Path)[ST_SIZE]
		OnePercSize = FileLength/100; OP = 0 #for showing percents


		UTF, SignatureLen = DetectByteOrderMark(Path)
		if Path.lower().endswith('.dz') or Path.lower().endswith('.gz'):
			FromDesc = gzip.open(Path, 'rb')
		else:
			FromDesc = open(Path, 'rb')
		
		FromDesc.read(SignatureLen) #skip UTF signature
		if not UTF and FileType != 'ann':
			EncFromHeader = ParseDSLHeader(FromDesc, UTF)
			FromDesc.seek(SignatureLen)
			if EncFromHeader : Encoding = EncFromHeader

		ToDesc = tempfile.TemporaryFile(mode='w+t', encoding='utf-8')
		while True :
			buf = FromDesc.read(10240)
			if not buf : break

			OP += 10240 #show percents
			if OP >= OnePercSize: print(str(FromDesc.tell()/OnePercSize)+'%', end='\r');sys.stdout.flush(); OP = 0

			if not UTF : buf = buf.decode(Encoding, errors='replace')
			else: buf = buf.decode(UTF, errors='replace')

			ToDesc.write(buf)
		ToDesc.seek(0)
		ParseDSLHeader(ToDesc, UTF)
		print('100%')
		return ToDesc

	except IOError as msg: terminate('\nCan\'t recode file to UTF-8. Error:\n'+str(msg),'\n')
	except UnicodeError : terminate("\nNot permitted symbol in the input file. Recode the file to UTF-16.")


def print_usage (stream, exit_code):
    print('Abbyy Lingvo 8 DSL to XDXF conversion\n\n' +
       'Usage: '+ProgramName+' options input_file output_directory\n', file=stream)
    print(
"""
 If a parameter surrounded with brackets - it's an optional parameter.

 [-h]               This help

 [-T] Dictionary type "translation"
 [-X] Dictionary type "explanatory"
 [-E] Dictionary type "encyclopedia"
 [-S] Dictionary type "spelling"
 [-A] Dictionary type "audio"

 [-n <name>]        Dictionary name (one word)
 [-k]               Keep the .xdxf file after zipping
 [--no-zip]         Do not create a zip file
 [-z <full_name>]   Full name of the dictionary, like it would appear on
                      the book cover. It may contain non-English symbols.
 [-d <descr>]       Short description
 [-f <from>]        "From" language
 [-t <to>]          "To" language
 [-a <file>]        Abbreviations file (if autodetect doesn't work)
 [-i]               Put visual indentation to the output file for human reading.

 Example:

 $ """ + ProgramName + """ -n General -E -d "My dictionary"\
-t English orig_dict.dsl /var/dicts""", file=stream)

    sys.exit(exit_code)



try : 
    optlist,args = getopt.getopt (sys.argv[1:], 'hTXESAn:z:d:f:t:a:ik', ['help', 'no-zip', 'keep'])
except getopt.GetoptError as msg:
    # If options fail, assume the arguments are just files
    optlist = []
    args = sys.argv[1:]

if not optlist and not args :
    print_usage(sys.stderr, 1)

for option, arg in optlist :

    if option == '-T':      # dictionary type - 'translation'
        if XMLHeaderData['type'] : XMLHeaderData['type'] += ', '
        XMLHeaderData['type'] += 'translation'

    elif option == '-X':      # dictionary type - 'explanatory'
        if XMLHeaderData['type'] : XMLHeaderData['type'] += ', '
        XMLHeaderData['type'] += 'explanatory'

    elif option == '-E':      # dictionary type - 'encyclopedia'
        if XMLHeaderData['type'] : XMLHeaderData['type'] += ', '
        XMLHeaderData['type'] += 'encyclopedia'

    elif option == '-S':      # dictionary type - 'spelling'
        if XMLHeaderData['type'] : XMLHeaderData['type'] += ', '
        XMLHeaderData['type'] += 'spelling'

    elif option == '-A':      # dictionary type - 'audio'
        if XMLHeaderData['type'] : XMLHeaderData['type'] += ', '
        XMLHeaderData['type'] += 'audio'

    elif option == '-n':      # -n dictionary name
        Name = arg      # if not specified, then takes from DSL: NAME

    elif option == '-z':      # -z full dictionary name
        XMLHeaderData['full_name'] = arg

    elif option == '-d':    # -d description
        XMLHeaderData['description'] = arg

    elif option == '-f':    # -f from language
        FromLanguage = arg  # if not specified, then takes from DSL: INDEX_LANGUAGE

    elif option == '-t':    # -t to language
        ToLanguage = arg    # if not specified, then takes from DSL: CONTENTS_LANGUAGE

    elif option == '-a':    # -a path to the abbreviations file
        AbbrevFile = arg


    elif option == '-i':    # -i put visual indentation
        NL = '\n'
        TB = '\t'

    elif option in ('-k', '--keep'):
        KeepXDXF = True

    elif option == '--no-zip':
        NoZip = True

    elif option in ('-h', '--help'):    # -h help
        print_usage(sys.stdout, 0)


if not XMLHeaderData['type'] :
    XMLHeaderData['type'] = 'explanatory' # Default to explanatory if not specified

if args.__len__() > 2:
    perror('\nToo many non option arguments.\n\n')
    print_usage (sys.stderr, 1)

if args.__len__() < 1:
    perror('\nToo few non option arguments.\n\n')
    print_usage (sys.stderr, 1)

if not os.path.exists(args[0]):
    perror(args[0], ' - not such file, or not a file.')
    sys.exit (1)

dsl_zip_ref = None
dsl_zip_names = set()
zip_path = args[0] + '.files.zip'
if not os.path.isfile(zip_path):
    zip_path = args[0] + '.dz.files.zip'
    
if os.path.isfile(zip_path):
    print("Found associated resources zip file: " + zip_path)
    try:
        dsl_zip_ref = zipfile.ZipFile(zip_path, 'r')
        dsl_zip_names = set(dsl_zip_ref.namelist())
    except Exception as e:
        print("Warning: Could not open zip file:", e)

#change current directory
try :
    os.chdir(os.path.dirname(args[0]) or os.curdir)
except OSError as msg: perror('Cant\'t change directory. Error: '+str(msg))

def DetectByteOrderMark(filename):
    """
    Opens and tests UTF file encoding:
    BOM_UTF8
    BOM_UTF16_BE
    BOM_UTF16_LE
    BOM_UTF32_BE
    BOM_UTF32_LE

    Returns: encoding, signature length
    If no signature found returns: None, 0
    """
    encodings = [ ( codecs.BOM_UTF32,   'utf-32',   4 ),
        ( codecs.BOM_UTF32_BE,  'utf-32-be',4 ),
        ( codecs.BOM_UTF32_LE,  'utf-32-le',4 ),
        ( codecs.BOM_UTF16_BE,  'utf-16-be',2 ),
        ( codecs.BOM_UTF16_LE,  'utf-16-le',2 ),
        ( codecs.BOM_UTF8,      'utf-8',    3 ) ]
    try :
        if os.path.isfile(filename) :
            f = open(filename,'rb')
            header = f.read(4) # Read just the first four bytes.
            f.close()
        else :
            perror('DetectByteOrderMark() - There\'s no file name:'+filename)
            sys.exit(1)
    except IOError as msg:
        perror('Can\'t test encoding of the file. Error:\n'+str(msg))
        sys.exit(1)

    for h,e,l in encodings :
        if header.find(h) == 0:
            return e,l
    return None, 0


try :
	#search and import annotation file
	for ann in os.listdir(os.getcwd()):
		if ann.lower() == os.path.splitext(ann.lower())[0]+'.ann' :
			print('\nFound annotation file: '+ann)
			AnnFileDesc = RecodeToUTF8(ann,'ann')

			if XMLHeaderData['description'] :
				print('Combining an annotation with a description, specified from command line.')
				XMLHeaderData['description'] += '\n\n'

			while True :
				strng = AnnFileDesc.readline()
				if not strng :
					AnnFileDesc.close()
					break
				XMLHeaderData['description'] += strng.strip()+'\n'

			XMLHeaderData['description'] += '\n\nThis dictionary was converted from Lingvo DSL format.\n'\
				'Converter script: '+ProgramName+' v.'+Version+' by Alexander Goryachev\nthorn_st@users.sourceforge.net'
			break
except IOError as msg: terminate("Problem with an annotation file: "+str(msg))


# Unescape logic for final file
def UnescapeXDXF(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Use a temporary placeholder for double backslashes
    content = content.replace('\\\\', '____DOUBLE_BACKSLASH____')
    # Single backslashes in DSL/XDXF context (like \[) should be removed
    # so that \[ becomes [
    content = content.replace('\\', '')
    # Restore double backslashes as single backslashes
    content = content.replace('____DOUBLE_BACKSLASH____', '\\')
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)


#open DSL file
DSLFileDesc = RecodeToUTF8(args[0],'dsl')


#--------------------- Writing XDXF dictionary header ---------------------
print('Creating XDXF dictionary header')

try :
    if FromLanguage :
        XMLHeaderData['lang_from'] = ShortLanguages[FromLanguage.lower()]
        FromLanguage = LongLanguages[FromLanguage.lower()]
except KeyError :
    terminate('Unknown language: ', FromLanguage, '\nPossible values are:\n',LongLanguages.keys(),'\n')

try :
    if ToLanguage :
        XMLHeaderData['lang_to'] = ShortLanguages[ToLanguage.lower()]
        ToLanguage = LongLanguages[ToLanguage.lower()]
except KeyError :
    terminate('Unknown language: ', ToLanguage, '\nPossible values are:\n',LongLanguages.keys(),'\n')


if not Name : 
    Name = DSL_Header_Info.get('name', 'dictionary')
if not FromLanguage : 
    FromLanguage = DSL_Header_Info.get('from', 'English')
if not ToLanguage : 
    ToLanguage = DSL_Header_Info.get('to', 'English')

if not Name : terminate('Can\'t find a dictionary name - specify it manually by -n option')
if not FromLanguage : terminate('Can\'t find a source language name - specify it manually by -f option')
if not ToLanguage : terminate('Can\'t find a target language name - specify it manually by -t option')
if not XMLHeaderData['description'] : XMLHeaderData['description'] = 'Dictionary "'+Name+'", imported from DSL format Lingvo'

Name = Name.lower()
if args.__len__() == 1:
    OutputDir = os.path.join(os.curdir, Name) #if not specified output directory, then use current
else : OutputDir = os.path.join(args[1], Name)

#create output directory
if not os.path.exists(OutputDir) :
    while True :
        yn = input('Path "'+os.path.abspath(OutputDir)+'" doesn\'t exists. Create? (y/n): ').lower().strip()
        if yn == 'y' : os.makedirs(OutputDir); break
        elif yn == 'n' : print('Cancelled by user.'); sys.exit(0)
        else : print("Enter only one symbol 'Y' or 'N' please.")


OutFileName = os.path.join(OutputDir, Name + '.xdxf')

#open an output xdxf file
try:
    outfile = open(OutFileName, 'w', encoding='utf-8')
except IOError as msg:
    perror('Cannot open output file: "'+OutFileName+'"\nError: '+str(msg))
    sys.exit (1);

print('\n'+'-'*40)
print('Source DSL-file: %s'			% args[0])
print('Output directory: %s'		% os.path.abspath(OutputDir))
print('Dictionary name: %s'			% Name)
print('Full dictionary name: %s'	% XMLHeaderData['full_name'])
#print('Description: %s'         % '\n'+'-'*20+'\n'+re.sub(r'<br />','\n',XMLHeaderData['description'])+'-'*20+'\n')
print('Source Language: %s'			% FromLanguage)
print('Target Language: %s'			% ToLanguage)
print('Dictionary type: %s'			% XMLHeaderData['type'])
#print('Transcription: %s'       % Trans)
print('-'*40, '\n')

try:
    import datetime
    date_str = datetime.datetime.now().strftime('%d-%m-%Y')

    outfile.write('<?xml version="1.0" encoding="UTF-8" ?>'+NL+
        '<!DOCTYPE xdxf SYSTEM "xdxf_strict.dtd">'+NL+
        '<xdxf revision="034">'+NL+
        '<meta_info>'+NL)

    outfile.write(
        TB+'<title>'+XMLHeaderData['full_name']+'</title>'+NL+
        TB+'<full_title>'+XMLHeaderData['full_name']+'</full_title>'+NL+
        TB+'<languages>'+NL+
        TB+TB+'<from xml:lang="'+XMLHeaderData['lang_from']+'"/>'+NL+
        TB+TB+'<to xml:lang="'+XMLHeaderData['lang_to']+'"/>'+NL+
        TB+'</languages>'+NL+
        TB+'<description>'+XMLHeaderData['description']+'</description>'+NL+
        TB+'<file_ver>001</file_ver>'+NL+
        TB+'<creation_date>'+date_str+'</creation_date>'+NL)

except IOError as msg: terminate("Can't write to the output file: "+str(msg))
#--------------------- end of XDXF header
Key = u''
SubArticle = False

def Replacement (matchobj):
	"""Tag replacer for re.sub"""

	global SubArticle

	#Subarticles
	subartbegin = re.search(r'\s+(?:\[\*\])*@\s*(.*)',matchobj.group(0))
	if subartbegin :
        #print('found subarticle'+subartbegin.group(1))
		if SubArticle :
			if  subartbegin.group(1).__len__(): return '</deftext>'+NL+TB+TB+'</def>'+NL+TB+TB+'<def>'+NL+TB+TB+'<k>'+subartbegin.group(1).strip()+'</k>'+NL+TB+TB+'<deftext>'
			else :
				SubArticle = False
				return '</deftext>'+NL+TB+TB+'</def>'
		SubArticle = True
		return '<def>'+NL+TB+TB+'<k>'+subartbegin.group(1).strip()+'</k>'+NL+TB+TB+'<deftext>'+NL

	#reference to another key-phrase
	reference =re.search(r'<<(.*?)>>',matchobj.group(0))
	if reference : return '<kref>'+reference.group(1)+'</kref>'

	#indentation
	indent =re.search(r'\[m(\d)\]',matchobj.group(0))
	if indent : return ' '*int(indent.group(1))
	#if indent : return ' '

	#colourings
	color = re.search(r'\[c\s+([a-zA-Z0-9#]+)\s*\]',matchobj.group(0))
	if color : return '<c c="'+color.group(1).lower()+'">'


	FileLink = re.search(r'\[s\](.+?)\[/s\]',matchobj.group(0))
	if FileLink :
		filename = FileLink.group(1).replace('\\', '/')
		print('Found reference to a file: '+filename)
		dest_dir = os.path.dirname(OutFileName)
		dest_file = os.path.join(dest_dir, filename)
		if not os.path.isfile(dest_file):
			try :
				if dsl_zip_ref and filename in dsl_zip_names:
					if NoZip: # Only extract if we are NOT going to reuse the zip later
						dsl_zip_ref.extract(filename, dest_dir)
				else:
					if os.path.isfile(filename):
						# Ensure parent directories exist
						os.makedirs(os.path.dirname(dest_file), exist_ok=True)
						shutil.copyfile(filename, dest_file)
					elif not dsl_zip_ref or filename not in dsl_zip_names:
						print("Warning: File not found:", filename)
			except Exception as msg: print("Warning: File link wasn't copied: "+str(msg))


		ext = os.path.splitext(filename)[1].lower()
		mimetype = ""
		if ext == '.spx': mimetype = 'audio/x-speex'
		elif ext == '.mp3': mimetype = 'audio/mpeg'
		elif ext == '.ogg': mimetype = 'audio/ogg'
		elif ext == '.wav': mimetype = 'audio/wav'
		elif ext == '.png': mimetype = 'image/png'
		elif ext == '.jpg' or ext == '.jpeg': mimetype = 'image/jpeg'
		elif ext == '.gif': mimetype = 'image/gif'
		
		type_attr = f' type="{mimetype}"' if mimetype else ""
		return f'<rref lctn="{filename}"{type_attr}/>'

	UrlLink = re.search(r'\[url\](.+?)\[/url\]', matchobj.group(0))
	if UrlLink : return '<iref href="'+UrlLink.group(1)+'">'+UrlLink.group(1)+'</iref>'

	LangID = re.search(r'\[\s*lang\s+id\s*\=\s*\d\s*\]',matchobj.group(0))
	if LangID : return ''

	RoofTilda = re.search(r'\^~',matchobj.group(0))
	if RoofTilda :
		return Key[:1].swapcase()+Key[1:].rstrip()

	Tilda = re.search(r'~',matchobj.group(0))
	if Tilda :
		return Key.rstrip()

	#all other tags
	return Tags[matchobj.group(0)]

def KillSlashes (matchobj):
    #double slashes
	DoubleSlashes =re.search(r'\\\\\\\\',matchobj.group(0))
	if DoubleSlashes : return '\\'

	#slashes
	Slash =re.search(r'\\\\',matchobj.group(0))
	if Slash : return ''


#--------------------- Process abbreviations ---------------------------
try :

	AbbrevFileDesc = 0
	if AbbrevFile:
		FileLength = os.stat(AbbrevFile)[ST_SIZE]
		AbbrevFileDesc = RecodeToUTF8(AbbrevFile,'abr')
	else:
		for AbbrevFile in os.listdir(os.getcwd()):
			if 'abbrev.dsl' in AbbrevFile.lower() or 'abrv.dsl' in AbbrevFile.lower() :
				while True :
					yn = input('Found an abbreviations file: "'+AbbrevFile+'" Import? (y/n): ').lower().strip()
					if yn == 'y' :
						FileLength = os.stat(AbbrevFile)[ST_SIZE]
						AbbrevFileDesc = RecodeToUTF8(AbbrevFile,'abr')
						break
					elif yn == 'n' : break
					else : print("Enter only one symbol 'Y' or 'N' please.")
				if AbbrevFileDesc : break


	if AbbrevFileDesc :
		print('Processing abbreviations')

		ArticleBegin = False

		Begin = True #begin of a file, before of any articles
		outfile.write('<abbreviations>'+NL)

		OnePercSize = FileLength/100; OP = 0 #for showing percents

		while True :
			strng = AbbrevFileDesc.readline()
			if not strng :
				AbbrevFileDesc.close()
				break

			OP += strng.__len__() #show percents
			if OP >= OnePercSize: print(str(AbbrevFileDesc.tell()/OnePercSize)+'%', end='\r');sys.stdout.flush(); OP = 0

			if not strng : continue

			if not strng[:1].isspace() and not ArticleBegin and not Begin:
				outfile.seek(-1,1)
				outfile.write('</abbr_v>'+NL+TB+'</abbr_def>'+NL)

			if not strng[:1].isspace() and not ArticleBegin:
				ArticleBegin = True
				outfile.write(TB+'<abbr_def>'+NL)
				Begin = False
				ValBegin = True

			if  not strng[:1].isspace() :
				outfile.write(TB+'<abbr_k>'+re.sub(r'(\\\\\\\\)|(\\\\)',KillSlashes,strng).strip()+'</abbr_k>'+NL)
				continue

			ArticleBegin = False

			if ValBegin == True : outfile.write(TB+TB+'<abbr_v>'); ValBegin = False

			strng = strng.strip()
			if strng : outfile.write(re.sub(r'(\\\\\\\\)|(\\\\)',KillSlashes,re.sub(TagsPattern,Replacement,strng))+'\n')
		outfile.seek(-1,1)
		outfile.write('</abbr_v>'+NL+TB+'</abbr_def>'+NL)
		outfile.write('</abbreviations>'+NL)
		print('100%')
except IOError as msg: terminate("Problem with an abbreviation file: "+str(msg))

outfile.write('</meta_info>'+NL+'<lexicon>'+NL)
#--------------------- End of process abbreviations ---------------------------

#--------------------- Process dictionary body ---------------------------
print('Processing dictionary body')


def FindInKeys (matchobj):
    """Tag replacer for re.sub"""

    #round brackets
    RoundBrackets =re.search(r'\((.*?)\)',matchobj.group(0))
    if RoundBrackets : return '<opt>'+RoundBrackets.group(1)+'</opt>'

    #curly brackets
    CurlyBrackets =re.search(r'\{(.*?)\}',matchobj.group(0))
    if CurlyBrackets : return CurlyBrackets.group(1)

Article = 0 #Articles counter
ArticleBegin = False
BufferCounter = 0

DefOpen = False #temporal crutch for tag <def>

#FleLength = os.stat(DSLFileDesc)[ST_SIZE]
SavePos = DSLFileDesc.tell()
DSLFileDesc.seek(0,2)
FileLength = DSLFileDesc.tell() - SavePos
DSLFileDesc.seek(SavePos)

OnePercSize = FileLength/100; OP = 0 #for showing percents



try :
	while  True :
		strng = DSLFileDesc.readline()
		if not strng :
			DSLFileDesc.close()
			break


		OP += strng.__len__() #show percents
		if OP >= OnePercSize: print(str(DSLFileDesc.tell()/OnePercSize)+'%', end='\r');sys.stdout.flush(); OP = 0

		if not strng : continue


		if not strng[:1].isspace() and not ArticleBegin and Article:
			DefOpen = False; outfile.write(TB+'</deftext>'+NL+TB+'</def>'+NL)#temporal crutch for tag <def>
			outfile.write('</ar>'+NL)

		if not strng[:1].isspace() and not ArticleBegin:
			Key = strng
			ArticleBegin = True
			Article += 1
			outfile.write('<ar>'+NL)

		if not strng[:1].isspace() :
			k_str = re.sub(r'(\\\\\\\\)|(\\\\)',KillSlashes,re.sub(SF+r'\((.*?)'+SF+r'\)|'+SF+r'\{(.*?)'+SF+r'\}',FindInKeys,strng)).strip()
			k_str = k_str.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
			outfile.write(TB+'<k>'+k_str+'</k>'+NL)
			continue

		ArticleBegin = False

		#temporal crutch for tag <def>
		if not DefOpen : outfile.write(TB+'<def>'+NL+TB+'<deftext>'+NL); DefOpen = True

		#strng = TB+TB+re.sub(TagsPattern,Replacement,strng.strip())
		strng = TB+TB+re.sub(TagsPattern,Replacement,strng)
		#if strng[-1:] == '>' : outfile.write(strng+NL)
		#else : outfile.write(strng+'\n'+NL)

		outfile.write(re.sub(r'(\\\\\\\\)|(\\\\)',KillSlashes,strng)+NL)
		#outfile.write(strng+NL)
	#--------------------- end of dictionary body

	outfile.write(TB+'</deftext>'+NL+TB+'</def>'+NL)#temporal crutch for tag <def>

	outfile.write('</ar>'+NL)
	outfile.write('</lexicon>'+NL)
	outfile.write('</xdxf>')
	print('100%')


except IOError as msg: terminate("Can't write to the output file: "+str(msg))

outfile.close()

# Final pass to unescape BEFORE zipping
UnescapeXDXF(OutFileName)

if dsl_zip_ref:
    dsl_zip_ref.close()

# ---- Phase 2: Zipping ----
if not NoZip:
    base_name = os.path.splitext(os.path.basename(args[0]))[0]
    if base_name.endswith('.dsl'): base_name = os.path.splitext(base_name)[0]
    
    # Place the zip INSIDE the output directory (the subdir)
    zip_path = os.path.join(OutputDir, base_name + '-xdxf.zip')
    zip_path = os.path.abspath(zip_path)
    
    print('\nCreating zip file: ' + zip_path)
    
    # If we have a source zip, we can try to "reuse" it by copying and appending
    # This is much faster for large resource files.
    source_zip = args[0] + '.files.zip'
    if not os.path.isfile(source_zip):
        source_zip = args[0] + '.dz.files.zip'
        
    if os.path.isfile(source_zip):
        print('Reusing resources from: ' + source_zip)
        shutil.copyfile(source_zip, zip_path)
        with zipfile.ZipFile(zip_path, 'a') as zf:
            zf.write(OutFileName, os.path.basename(OutFileName))
            # Also add any files from OutputDir that might not be in the zip
            # (e.g. files copied from filesystem)
            for root, dirs, files in os.walk(OutputDir):
                for f in files:
                    if f != os.path.basename(OutFileName):
                        if f not in zf.namelist():
                            zf.write(os.path.join(root, f), f)
    else:
        # Create a new zip and add everything
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(OutputDir):
                for f in files:
                    zf.write(os.path.join(root, f), f)

    if not KeepXDXF:
        print('Cleaning up temporary files in: ' + OutputDir)
        # We only remove the .xdxf file, but keep the directory and the zip
        if os.path.exists(OutFileName):
            os.remove(OutFileName)
        # Also remove any bmp icons if we want? No, let's keep the directory structure
        # actually the user said "moved to dictionary/". 
        # So we want the ZIP to be the result.
        # If KeepXDXF is false, we can just leave the zip in the folder.
    else:
        # If keeping, do nothing
        pass

#search and copy dictionary icon file
for pic in os.listdir(os.getcwd()):
	if pic.lower() == os.path.splitext(pic.lower())[0]+'.bmp' :
		print('\nFound an icon file: '+pic)
#copy icon to the output directory with the name of the base dictionary and "bmp" extention
		try :
			shutil.copyfile(pic, os.path.splitext(OutFileName)[0]+'.bmp')
		except IOError as msg: terminate("The dictionary icon wasn't copied: "+str(msg))
		print('The dictionary icon file copied as: "'+os.path.basename(os.path.splitext(OutFileName)[0]+'.bmp')+'"')
		break


print('\n\n***SUCCESS***\n')

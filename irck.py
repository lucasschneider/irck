#!/usr/bin/env python
import argparse
import os
import re
import ntpath
from PyPDF2 import PdfFileWriter, PdfFileReader
import pdf2image
try:
    from PIL import Image
except ImportError:
    import Image
import pytesseract

class readable_dir(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        prospective_dir=values
        if not os.path.isdir(prospective_dir):
            raise argparse.ArgumentTypeError("readable_dir: {0} is not a valid path".format(prospective_dir))
        if os.access(prospective_dir, os.R_OK):
            setattr(namespace,self.dest,prospective_dir)
        else:
            raise argparse.ArgumentTypeError("readable_dir: {0} is not a readable dir".format(prospective_dir))

class valid_libcode(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        for libcode in values:
            libcode=libcode.lower()
            if not re.match("^(?:haw|hpb|lak|mad|mea|msb|pin|seq|smb)$",libcode):
                raise argparse.ArgumentTypeError("valid_libcode: {0} is not a valid Madison library code".format(libcode))
        setattr(namespace,self.dest,values)

parser = argparse.ArgumentParser(description='Verify the file names in a directory for properly formatted MPL Incident Report filenames.')
parser.add_argument('-d', '--directory', default='./', action=readable_dir, help='The directory of files to parse.')
parser.add_argument('-v', '--verify', default=False, action='store_true', help='Only return invalid filenames. This is the default.')
parser.add_argument('-l', '--libcode', nargs="+", action=valid_libcode, help='Enter a three letter MPL library code to filter results.')
surname_group = parser.add_mutually_exclusive_group()
surname_group.add_argument('-s', '--surname', nargs="+", help='Filter by a patron\'s surname; all surnames listed must be in the filename.')
surname_group.add_argument('-S', '--surname-or', dest='surname_or', nargs="+", help='Filter by a patron\'s surname; one of the surnames listed must be in the filename.')
surname_group.add_argument('-u', '--lnu', dest='lnu', action='store_true', help='Only select LNU incidents')
surname_group.add_argument('-U', '--no-lnu', dest='lnu', action='store_false',  help='Filter out LNU incidents')
parser.set_defaults(lnu=None)
functions_group = parser.add_mutually_exclusive_group()
functions_group.add_argument('-m', '--merge', default=False, action='store_true', help='Attempt to merge related files')
functions_group.add_argument('--ocr', nargs="+", help='Path(s) to file(s) on which to perform OCR.')

def build_regex(args):
    noverify_regex = ""

    date = "(?:199[0-9]|20[01][0-9])-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
    time = "(?:T(?:[01][0-9]|2[0-4]):[0-5][0-9])?"

    if args.libcode is not None:
        lib = "_(?:" + '|'.join(args.libcode) + ")";
        noverify_regex += lib
    else:
        lib = "_(?:haw|hpb|lak|mad|mea|msb|pin|seq|smb)"

    if args.lnu is not None and args.lnu:
        surname = "_LNU(?:-1?[0-9])?"
    elif args.lnu is not None and not args.lnu:
        surname = "_(?:(?:[a-z]+(?:-[a-z]+){,4})(?:-1?[0-9])?)(?:_(?:(?:[a-z]+(?:-[a-z]+){,4})(?:-1?[0-9])?))*"
    elif args.surname is not None:
        surname = '_' + '_'.join(args.surname)
    elif args.surname_or is not None:
        surname = "_(?:" + '|'.join(args.surname_or) + ")";
        surname = surname
    else:
        surname = "(?:_(?:(?:[a-z]+(?:-[a-z]+){,4})|LNU)(?:-1?[0-9])?)(?:(?:_(?:(?:[a-z]+(?:-[a-z]+){,4})|LNU)(?:-1?[0-9])?))*"
    noverify_regex += surname

    if args.merge is not None and args.merge:
        part = "_part\\d"
        noverify_regex += part
    else:
        part = "(?:_(?:part)?\\d)?"

    if args.verify:
        return  "^" + date + time + lib + surname + part + "\\.pdf$"
    else:
        return ".*" + noverify_regex + ".*"

def path_leaf(path):
    head, tail = ntpath.split(path)
    return tail or ntpath.basename(head)

def process_ocr(pdf_file):
    images = pdf2image.convert_from_path(pdf_file)
    output = ""
    for pg, img in enumerate(images):
        output += pytesseract.image_to_string(img)
    return output

def merge_results(file_string):
    print("\n" + file_string)
    confirm = input("Would you like to merge the file above with their respective parts? [y/N]: ")

    if confirm == "y" or confirm == "Y":
        print("\nAttempting to merge PDFs...\n")
        merge_list = []
        temp_list = []
        previous_file_base = ""

        for idx,file in enumerate(file_string.split("\n")):
            if (file[:-10] != previous_file_base):
                if idx > 0:
                    merge_list.append(temp_list)
                temp_list = [file]
            else:
                temp_list.append(file)
            previous_file_base = file[:-10]

        for file_parts in merge_list:
            merged_filename = file_parts[0][:-10] + ".pdf"
            pdfWriter = PdfFileWriter()
            if len(file_parts) > 1:
                for file in file_parts:
                    pdfFileObj = open(file,'rb') # open with 'read, binary'
                    pdfReader = PdfFileReader(pdfFileObj)
                    for page in range(pdfReader.numPages):
                        pageObj = pdfReader.getPage(page)
                        pdfWriter.addPage(pageObj)
                    os.remove(file)
                pdfOutput = open(merged_filename, 'wb') # open with 'write binary'
                pdfWriter.write(pdfOutput)
                pdfOutput.close()
                print("Created `" + merged_filename + "` and deleted parts.")
            else:
                print(file_parts[0][:-10] + " does not have multiple parts. Skipped.")
    else:
        print("\n=== Merger not attempted. ===\n")

args = parser.parse_args()
regex = build_regex(args)

pdf_count = 0
pdf_match = 0
filelist = ""

if args.ocr is not None:
    for filepath in args.ocr:
        if os.path.exists(filepath) and filepath.endswith('.pdf'):
            if not os.path.exists('ocr_output'):
                os.mkdir('ocr_output')
            if not os.path.exists('ocr_processed_pdfs'):
                os.mkdir('ocr_processed_pdfs')
            with open("ocr_output/" + path_leaf(filepath)[:-4]+".txt", "w") as output_file:
                print(process_ocr(filepath), file=output_file)
            os.rename(filepath, "ocr_processed_pdfs/" + filepath)
        else:
            print(filepath + " is not a valid PDF.")
else:
    for file in sorted(os.listdir(args.directory)):
        if file.endswith(".pdf"):
            pdf_count += 1
            x = re.match(regex, file)
            if (args.verify and not x) or (not args.verify and x):
                pdf_match += 1
                filelist += file + "\n"

    msg = ""

    if args.merge:
        if pdf_match == 0:
            print("\n=== No files in this directory need to be merged. ===\n")
        elif pdf_match == 1:
            print("\n=== No related parts matched this file. ===\n")
            print(filelist)
        else:
            merge_results(filelist)
    elif pdf_count == 0:
        print("\n=== No PDFs were found in this directory ===\n")
    elif pdf_match == 0 and args.verify:
        print("\n=== All PDF files are properly named ===\n")
    elif pdf_match > 0 and args.verify:
        if pdf_match == 1:
            msg = "\n=== " + str(pdf_match) + " of " + str(pdf_count) + " PDF is invalid ===\n"
        else:
            msg = "\n=== " + str(pdf_match) + " of " + str(pdf_count) + " PDFs are invalid ===\n"
        print(msg + "\n" + filelist + msg)
    elif pdf_match > 0:
        if pdf_match == 1:
            msg = "\n=== " + str(pdf_match) + " of " + str(pdf_count) + " PDF matches ===\n"
        else:
            msg = "\n=== " + str(pdf_match) + " of " + str(pdf_count) + " PDFs match ===\n"
        print(msg + "\n" + filelist + msg)
    else:
        print("\n=== No matching PDFs were found ===\n")

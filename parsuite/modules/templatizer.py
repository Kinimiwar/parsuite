from parsuite.core.argument import Argument,DefaultArguments
from parsuite import helpers
from parsuite.core.suffix_printer import *
from sys import exit,stderr,stdout
from pathlib import Path
import csv
import re
import pdb
from base64 import b64encode
from urllib.parse import quote as url_encode

class Offsets(dict):

    def ilookup(self,index):
        for k,v in self.items():
            if v == index: return k

        return None

TRANSFORMS = ['b64_encode','url_encode']

help ='''Accept a series of text templates and update their
values. It ingests a CSV file, making the values of each field
available to each template.
'''

args = [
    Argument('--text-templates','-tts',
        nargs='+',
        required=True,
        help='''Space delimited strings or file names. Content from
        files will be slurped from disk and updated accordingly. Values
        from the CSV file are accessed using this type of injection
        scheme: <<<:{field_name}:>>>, where field_name is a column header.
        Generate random values by inserting this scheme: <<<:RAND:>>>.
        Additionally, If the same random value needs to be shared between
        each template, suffix the random injection scheme with an integer
        value: <<<:RAND1:>>>.
        '''),
    Argument('--csv-file','-csv',
        required=True,
        help='''CSV file containing values that will be placed in
        template replacement fields. A header row must be included
        in the CSV such that each column can be identified.
        '''),
    Argument('--out-csv','-o',
        help='''Output file that will receive output records.
        '''),
    Argument('--out-mode','-om',
        default='overwrite',
        choices=['overwrite','append'],
        help='Output mode, options: %(default)s'),
    Argument('--random-length','-rl',
        default=10,
        type=int,
        help='''Length of random values generated.
        Default: %(default)s''')
]

USED_RANDOMS = UR = []

def b64_encode(val):

    return b64encode(bytes(val,'utf8')).decode('utf8')

def encode(val, encoder=None):

    if not encoder: return val
    return globals()[encoder](val)

def parse(text_templates,csv_file,random_length,out_csv,
        out_mode,*args, **kwargs):

    # ==========================
    # CAPTURE ALL TEMPLATE FILES
    # ==========================

    tts = text_templates
    for n in range(0,tts.__len__()):
        try:
            if Path(tts[n]).exists():
                with open(tts[n]) as infile: tts[n] = infile.read()
        except:
            pass

    # ============================
    # PARSE CSV AND EXTRACT HEADER
    # ============================

    header, csv_lines = [], []
    with open(csv_file) as csvfile:
        csv_lines = [l for l in csv.reader(csvfile)]
        headers = csv_lines.pop(0)
    
    STRAND_RE = 'RAND([0-9]+)?'

    # ===============================
    # BUILD FIELD REGULAR EXPRESSIONS
    # ===============================

    FIELD_RE = '<{3}:('+'|'.join(headers)
    FIELD_RE += f'|{STRAND_RE}):'
    FIELD_RE += '(---('+'|'.join(TRANSFORMS)+'))?>{3}'
    FIELD_RE = re.compile(FIELD_RE)

    # ======================================
    # CALCULATE VALUE OFFSETS IN EACH RECORD
    # ======================================

    offsets = Offsets()
    ind = 0
    for h in headers:
        offsets[h] = ind
        ind += 1

    # ========================================
    # UPDATE EACH TEXT TEMPLATE FROM CSV FILES
    # ========================================

    '''
    # Handling referenceable random values

    - allow user to supply rand fields
    - the rand fields can be suffixed with an integer value
    - generate a random value for each random field
    - can then accessing that random value by reusing the
      suffixed value, i.e. the same value will replace all
      references to all fields labeled rand1
    - a field simply labeled "RAND" will receive a random
      value

    # General logic

    1. iterate over each template
    2. detect each random part
    3. generate a value for each random
    4. iterate over each template again
    5. make replacements for each field
    '''

    if out_mode == 'overwrite': out_mode = 'w'
    else: out_mode = 'a'

    outfile = open(out_csv, out_mode)
    csv_writer = csv.writer(outfile)

    try:

        used_randoms = []
        for row in csv_lines:
    
            rands = {}
            out_fields = []
            for template in text_templates:
    
                replaced = []
                for match in re.finditer(FIELD_RE,template):
    
                    # ==================
                    # TRACK REPLACEMENTS
                    # ==================
                    encoder = match.groups()[2]
                    if encoder: encoder = encoder[3:]
    
                    '''
                    Track which replacements have been made, assuring
                    a given replacement is performed only once. This
                    is for efficiency. Normal RAND fields should always
                    be handled.
                    '''
                    field = match.string[match.span()[0]:match.span()[1]]
                    
                    if not field.startswith('<<<:RAND:') and field in replaced:
                        continue
                    
                    if not field.startswith('<<<:RAND:'): replaced.append(field)
    
                    # ===================================
                    # IDENTIFY AND HANDLE A RANDOM FIELDS
                    # ===================================
    
                    imatch = re.search(STRAND_RE,field)
                    if imatch and imatch.groups()[0]:
    
                        # Extract the rkey
                        rkey = rand_key = imatch.groups()[0]
    
                        # Generate a random for the suffixed field
                        if not rkey in rands:
                            used_randoms.append(
                                helpers.gen_rand(random_length,used_randoms)
                            )
                            rands[rkey] = used_randoms[-1]
            
                        # Make all replacements for the random field of that rkey
                        template = re.sub(field,
                                encode(rands[rkey],encoder),
                                template)
    
                    elif imatch:
    
                        # Get a new random value
                        used_randoms.append(
                            helpers.gen_rand(random_length,used_randoms)
                        )
    
                        # Replace the first RAND field with the latest random value
                        template = re.sub(field,
                                encode(used_randoms[-1],encoder),
                                template,1)
    
                    if imatch: continue
    
                    # ==============================
                    # IDENTIFY AND HANDLE CSV FIELDS
                    # ==============================
    
                    template = template.replace(field,
                            encode(row[offsets[match.groups()[0]]],encoder)
                    )

                out_fields.append(template)

            csv_writer.writerow(out_fields)


    finally:

        outfile.close()

    return 0
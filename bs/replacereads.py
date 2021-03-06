#!/usr/bin/env python

import sys,pysam,argparse
from random import randint

def cleanup(read,RG):
    '''
    fixes unmapped reads that are marked as 'reverse'
    fill in read group at random from existing RGs if 
    RG tags are present in .bam header 
    '''

    # may need more testing
    if read.is_unmapped and read.is_reverse:
        read.is_reverse = False
    if read.mate_is_unmapped and read.mate_is_reverse:
        read.mate_is_reverse = False

    if RG:
        hasRG = False
        for tag in read.tags:
            if tag[0] == 'RG':
                hasRG = True

        if not hasRG:
            # add random read group from list in header
            newRG = RG[randint(0,len(RG)-1)]
            read.tags = read.tags + [("RG",newRG)]
    return read

def getRGs(bam):
    '''return list of RG IDs'''
    RG = []
    if 'RG' in bam.header:
        for headRG in bam.header['RG']:
            RG.append(headRG['ID'])
    return RG

def getExcludedReads(file):
    '''read list of excluded reads into a dictionary'''
    ex = {}
    f = open(file,'r')
    for line in f:
        line = line.strip()
        ex[line] = True
    f.close()
    return ex

#replaceReads(targetbam, donorbam, outputbam, args.namechange, args.exclfile, args.all, args.keepqual, args.progress)
def replaceReads(targetbam, donorbam, outputbam, nameprefix=None, excludefile=None, allreads=False, keepqual=False, progress=False):
    ''' targetbam, donorbam, and outputbam are pysam.Samfile objects
        outputbam must be writeable and use targetbam as template
        read names in excludefile will not appear in final output
    '''
    RG = getRGs(targetbam) # read groups

    exclude = {}
    if excludefile:
        exclude = getExcludedReads(excludefile)

    # load reads from donorbam into dict 
    sys.stderr.write("loading donor reads into dictionary...\n")
    nr = 0
    rdict = {}
    excount = 0 # number of excluded reads
    nullcount = 0 # number of null reads
    for read in donorbam.fetch(until_eof=True):
        if read.seq: # sanity check - don't include null reads
            if read.qname not in exclude:
                pairname = 'F' # read is first in pair
                if read.is_read2:
                    pairname = 'S' # read is second in pair
                if not read.is_paired:
                    pairname = 'U' # read is unpaired
                if nameprefix:
                    qual = read.qual # temp
                    read.qname = nameprefix + read.qname # must set name _before_ setting quality (see pysam docs)
                    read.qual = qual
                extqname = ','.join((read.qname,pairname))
                rdict[extqname] = read
                nr += 1
            else: # excluded
                excount += 1
        else: # no seq!
            nullcount += 1

    sys.stderr.write("loaded " + str(nr) + " reads, (" + str(excount) + " excluded, " + str(nullcount) + " null-->ignored)\n")

    excount = 0
    recount = 0 # number of replaced reads
    used = {}
    prog = 0
    for read in targetbam.fetch(until_eof=True):

        prog += 1
        if progress and prog % 10000000 == 0:
            sys.stderr.write("processed " + str(prog) + " reads.\n")

        if read.qname not in exclude:
            pairname = 'F' # read is first in pair
            if read.is_read2:
                pairname = 'S' # read is second in pair
            if not read.is_paired:
                pairname = 'U' # read is unpaired
            if nameprefix:
                qual = read.qual # temp
                read.qname = nameprefix + read.qname
                read.qual = qual

            extqname = ','.join((read.qname,pairname))
            if extqname in rdict: # replace read
                if keepqual:
                    rdict[extqname].qual = read.qual
                rdict[extqname] = cleanup(rdict[extqname],RG)
                outputbam.write(rdict[extqname])  # write read from donor .bam
                used[extqname] = True
                recount += 1
            else:
                read = cleanup(read,RG)
                outputbam.write(read) # write read from target .bam
        else:
            excount += 1

    sys.stderr.write("replaced " + str(recount) + " reads (" + str(excount) + " excluded )\n")

    nadded = 0
    # dump the unused reads from the donor if requested with --all
    if allreads:
        for extqname in rdict.keys():
            if extqname not in used and extqname not in exclude:
                rdict[extqname] = cleanup(rdict[extqname],RG)
                outputbam.write(rdict[extqname])
                nadded += 1
        sys.stderr.write("added " + str(nadded) + " reads due to --all\n")

def main(args):
    targetbam = pysam.Samfile(args.targetbam, 'rb')
    donorbam  = pysam.Samfile(args.donorbam, 'rb')
    outputbam = pysam.Samfile(args.outputbam, 'wb', template=targetbam)

    replaceReads(targetbam, donorbam, outputbam, args.namechange, args.exclfile, args.all, args.keepqual, args.progress)

    targetbam.close()
    donorbam.close()
    outputbam.close()

if __name__=='__main__':
    parser = argparse.ArgumentParser(description='replaces aligned reads in bamfile1 with aligned reads from bamfile2')
    parser.add_argument('-b', '--bam', dest='targetbam', required=True,
                        help='original .bam')
    parser.add_argument('-r', '--replacebam', dest='donorbam', required=True,
                        help='.bam with reads to replace original bam')
    parser.add_argument('-o', '--outputbam', dest='outputbam', required=True, 
                        help="name for new .bam output")
    parser.add_argument('-n', '--namechange', dest='namechange', default=None, 
                        help="change all read names by prepending string (passed as -n [string])")
    parser.add_argument('-x', '--exclude', dest='exclfile', default=None,
                        help="file containing a list of read names to ignore (exclude from output)")
    parser.add_argument('--all', action='store_true', default=False, 
                        help="append reads that don't match target .bam")
    parser.add_argument('--keepqual', action='store_true', default=False, 
                        help="keep original quality scores, replace read and mapping only")
    parser.add_argument('--progress', action='store_true', default=False,
                        help="output progress every 10M reads")
    args = parser.parse_args()
    main(args)

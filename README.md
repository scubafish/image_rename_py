# image_rename
A Python script that uses ExifTool to bulk rename images from supported cameras based on a set of rules. This is a rewrite of a script I previously wrote years ago in Perl, and is still a work in progress.

This script requires that ExifTool (https://www.sno.phy.queensu.ca/~phil/exiftool/) is installed on your system and it also requires the Python Exif library PyExifTool (https://smarnach.github.io/pyexiftool/).

The purpose is to rapidly bulk rename images from digital cameras into a useful name format by using Exif data and, in some cases, existing file name information when Exif data is not available.

The input is a set of image names from digital cameras, phones, etc, which are all normalized and renamed and moved into sub directories with the following name format: YYYYMMDD/YYYYMMDD_HH_MM_SS_CAMERAMODEL_FILENUMBER.EXT

Examples outputs would be:

20101123/20101123_18_19_48_5DM2_7321.CR2

20160512/20160512_06_13_04_5DM2_7235.MOV

20160512/20160512_06_13_04_5DM2_7235.THM

20160507/20160507_13_32_42_7DM2_3862.CR2

20110904/20110904_21_35_36_7D_0791.CR2

20080518/20080518_12_50_52_G9_1553.CR2

20130707/20130707_19_03_18_EOSM_6173.MOV

20130707/20130707_19_01_47_EOSM_6162.CR2

20170424/20170424_10_26_38_S7.jpg

20161016/20161016_09_16_06_GPRO.JPG

20161016/20161016_09_16_08_GPRO.JPG

The script uses a table of supported camera models (found in the Exif data) to help figure out naming logic and special case some camera types. This is especially useful for normalizing names across multiple camera models and for creating logical file names for timelapse photography input when there may be 30,000+ thousand photographs to organize.

It also includes features to adjust the timestamp on the generated filenames in case your camera's date and time was not set correctly.

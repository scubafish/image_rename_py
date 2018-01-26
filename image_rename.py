#!/usr/bin/python3

# Either use the system exiftool, or specify path on command line, or specify path here
#exiftoolpath = "/foo/Image-ExifTool-9.67/"
exiftoolpath = ""

verbose = False

# Currently supported camera models and mapped names are:
#
# Canon EOS 5D Mark II : 5DM2
# Canon EOS 7D : 7D
# Canon EOS 7D Mark II : 7DM2
# Canon PowerShot G9 : G9
# GoPro AVC encoder : GPRO    Hero 2 video mode
# YHDC5170 : GPRO             Hero 2 image mode
# SCH-I500 : I500             Galaxy S2 / Fascinate
# Canon EOS M : EOSM
# SCH-I545 : S4
# SM-G930V : S7
# Canon PowerShot G1 X Mark II : G1X2
# FinePix4700 ZOOM : FP4700
# iPhone 6
# Panasonic SZ-25
#
#
# Sample output file names are:
#
# 20101123_18_19_48_5DM2_7321.CR2
# 20160512_06_13_04_5DM2_7235.MOV
# 20160507_13_32_42_7DM2_3862.CR2
# 20160510_11_18_25_7DM2_0630.MOV
# 20110831_22_04_31_7D_9978.MOV
# 20110904_21_35_36_7D_0791.CR2
# 20080518_12_50_52_G9_1553.CR2
# 20080518_13_09_06_G9_1556.AVI
# 20130707_19_03_18_EOSM_6173.MOV
# 20130707_19_01_47_EOSM_6162.CR2
# 20170424_10_26_38_S7.jpg
# 20170424_09_41_05_S7.mp4
# 20160514_10_22_57_S4.mp4
# 20160514_10_40_58_S4.jpg

# Image data dictionary keys:
# year
# month
# day
# hour
# minute
# second
# sequence            This is the image sequence number for multiple images taken at the same time
# camera_model_mapped This is the mapped model name as it appears in the file name
# camera_model_exif   This is the model name as it appears in the exif
# file_extension

import sys
import argparse
import subprocess
import os
import shutil
from copy import deepcopy
from datetime import datetime
from datetime import timedelta
import exiftool


def v_print(message):
	if verbose == True:
		print(message)

	return


# Much of the time all you need to do is add a new entry here
# amd the rest of the script will "just work". The hiccup is
# when other fields (date/etc) are in exif keys or sidecar files
# that need to be special cased.
#
# Also note that if special rules are not required for your new camera
# model it may be OK to use the --camera option on the command line to
# specify a new one for the file name. If all other fields (date, etc) can
# be found this will also allow for a new camera name to be specified
# without modifying the code
#
def camera_name_map(argument):
	switcher = {
		"Canon EOS 5D Mark II"         : "5DM2",
		"Canon EOS 7D"                 : "7D",
		"Canon EOS 7D Mark II"         : "7DM2",
		"Canon PowerShot G1 X Mark II" : "G1X2",
		"Canon PowerShot G9"           : "G9",
		"Canon EOS M"                  : "EOSM",
		"GoPro AVC encoder"            : "GPRO",
		"YHDC5170"                     : "GPRO",
		"SCH-I500"                     : "I500",  # For legacy reasons this is the I500, and not S2
		"SCH-I545"                     : "S4",
		"SM-G930V"                     : "S7",
		"FinePix4700 ZOOM"             : "FP4700",
		"DMC-ZS25"                     : "ZS25",
		"iPhone 6"                     : "IPHONE6",
	}

	return switcher.get(argument, "unknown")

# Get the model name from the EXIF data and map it to a name
# that will be stored in the destination file
#
def get_camera_model(metadata, image_data):

#	for key in metadata:
#		print("   ", key, ":", metadata[key])

	model_from_file = metadata.get('EXIF:Model')

	if not model_from_file:
		# 5DM2 .MOVs store model name here
		model_from_file = metadata.get('QuickTime:Model')

	if not model_from_file:
		# The GoPro Hero 2 videos uses Compressor Name for the model
		# Compressor Name : GoPro AVC encoder
		model_from_file = metadata.get('QuickTime:CompressorName')

#	print("Model name from file:", model_from_file, "Mapped Name:", camera_name_map(model_from_file))

	image_data["model_exif"] = model_from_file
	image_data['model_mapped'] = camera_name_map(model_from_file)

	return

# Grab the file creation date from EXIF data and pull apart it's
# components into year, month, day, etc which will be used for
# file name creation later
# Expected format: 2018:01:19 14:36:17
#
def get_date(metadata, image_data):
	filedate = metadata.get("EXIF:DateTimeOriginal")
	if not filedate:
		# The GoPro uses Create Date instead
		filedate = metadata.get("QuickTime:MediaCreateDate")

	if not filedate:
		return 1

#	print("date: ", filedate)
	datetime_object = datetime.strptime(filedate, "%Y:%m:%d %H:%M:%S")
#	print(datetime_object.timetuple())

	image_data["year"] = datetime_object.timetuple().tm_year
	image_data["month"] = datetime_object.timetuple().tm_mon
	image_data["day"] = datetime_object.timetuple().tm_mday
	image_data["hour"] = datetime_object.timetuple().tm_hour
	image_data["minute"] = datetime_object.timetuple().tm_min
	image_data["second"] = datetime_object.timetuple().tm_sec

	return 0

# We know that some files, like the videos on the S4 and S7, use timestamps
# that are GMT instead of local time. Since I want to make sure I remember
# to use localtime in the filenames this function checks if a skew was set
# which can be used to remind me to set one for those video types.
#
def skew_set(skew_days, skew_hours, skew_mins, skew_secs):
	if (skew_days != 0) or (skew_hours != 0) or (skew_mins != 0) or (skew_secs != 0):
		return True

	return False

# Adjust date and time based on a user spuulied skew value, if any were provided.
# This will allow for adjusting a timestamp in the file name in case
# the clock on the camera was off.
#
def add_skew(image_data, metadata, skew_days, skew_hours, skew_mins, skew_secs):
	if (skew_days != 0) or (skew_hours != 0) or (skew_mins != 0) or (skew_secs != 0):
		print("Adding skew of %d days %d hours %d minutes %d seconds" % (skew_days, skew_hours, skew_mins, skew_secs))

	datetime_object = datetime(image_data['year'], image_data['month'], image_data['day'], image_data['hour'], image_data['minute'], image_data['second'])
#	print("DATE ORIG :", datetime_object)

	datetime_object = datetime_object + timedelta(0, skew_secs + (skew_mins * 60) + (skew_hours * 3600) + (skew_days * 86400))
#	print("DATE AFTER:", datetime_object)

	# If the camera is the S7 and this is a video then the timestamp
	# from the file name is the end of the video, we want it to be
	# the beginning. Grab the duration from exif and subtract it.
	if (image_data.get('file_extension').upper() == "MP4") and (image_data.get('model_mapped').upper() == "S7"):
		# TODO - which duration?
		# QuickTime:TrackDuration : 20.792
		# QuickTime:Duration : 21.013
		# QuickTime:MediaDuration : 21.0133333333333

		duration = metadata.get("QuickTime:Duration")
#		print("Duration:", duration)
		datetime_object = datetime_object + timedelta(0, -duration)

	image_data["year"] = datetime_object.timetuple().tm_year
	image_data["month"] = datetime_object.timetuple().tm_mon
	image_data["day"] = datetime_object.timetuple().tm_mday
	image_data["hour"] = datetime_object.timetuple().tm_hour
	image_data["minute"] = datetime_object.timetuple().tm_min
	image_data["second"] = datetime_object.timetuple().tm_sec

	return

# Check for the 2 special cases where the S7 puts file numbers in the file name
# _NNN or (N) at the end of the file.
#
# TODO - can probably use the same code for the S4, need to check
#
def get_filenumber_s7(metadata, image_data, filenumber):
#	print("S7 looking for _NNN")

	# First check for _NNN
	tmp_filenumber = image_data.get('file_name').rsplit('_', 1)[1]

#	print(tmp_filenumber, "len:", len(tmp_filenumber))

	if (len(tmp_filenumber) == 3) and tmp_filenumber.isdigit():
#		print("File number found fom S7")
		filenumber = tmp_filenumber

	# Nope. Now try the (N) version for the S7
	if (filenumber == "None"):
#		print("S7 checking for (N)")

		if "(" in image_data.get('file_name'):
			tmp_filenumber = image_data.get('file_name').rsplit('(', 1)[1]

			if ")" in tmp_filenumber:
				tmp_filenumber = tmp_filenumber.rsplit(')', 1)[0]
#				print(tmp_filenumber, "len:", len(tmp_filenumber))

				if tmp_filenumber.isdigit():
					filenumber = tmp_filenumber

	return filenumber


# Grab the file number if there is one
# The 5DM2 does not insert the file number in the MOV or THM files.
# Need to get those from the file name.
#
# The EOS M does not insert file number in CR2 file
#
# The 5DM2 inserts this value in two places for CR2/JPG:
#    MakerNotes:FileIndex : 9049
#    Composite:FileNumber : 100-9049
#
#    Note with the 5DM2 when the file number rolls to 0001 the exif numbers are 10000:
#    MakerNotes:FileIndex : 10000
#    omposite:FileNumber : 100-10000
#
# But turns to 0002 on the next image:
#    MakerNotes:FileIndex : 2
#    Composite:FileNumber : 101-0002
#
# The 5DM2 does not however insert a file number into the MOV or THM
# for videos, so it has to be fetched from the file name.
#
# The 7D stores it in one place:
#    Composite:FileNumber : 100-0841
#
# The 7DM2 doesn't store it in the exif
#
# The G1XMKII and G9 Stores in one place:
# (NOTE it is more than 4 digits though. TODO truncate to 4? The file name contains 1387
#    MakerNotes:FileNumber : 1011387
#
# as well as the file name, but other models only keep it in the file name. The code has
# to look in multiple spots. If the one in the exif exists use that one, otherwise just try
# and get it from the file name
#
def get_filenumber(metadata, image_data):
	filenumber = str(metadata.get('Composite:FileNumber'))

	if filenumber == "None":
		filenumber = str(metadata.get('MakerNotes:FileNumber'))

	if filenumber != "None":
		# At this point we might have a file number in one of these formats:
		# 100-9049
		# 100-10000
		# 101-0002
		# 1011387
		#
		# Now normalize it to a 4 digit number

		# Force it to be a string so we can look for special characters without
		# Python puking
		filenumber = str(filenumber)

		if "-" in filenumber:
			filenumber = filenumber.rsplit("-", 1)[1]
#			print("SPLIT FILE NUMBER:", filenumber)

			if filenumber == '10000':
				# Special case of 100-10000 when number wraps
#				print("Converting from 10000 to 0001")
				filenumber = '0001'

	# We don't have a file number, but do have an image from a camera
	# model that uses a number at the end of the file name then parse that.
	# Add new models here.
	if (filenumber == "None") and \
		((image_data.get('model_exif') == "Canon EOS 5D Mark II") or \
		 (image_data.get('model_exif') == "Canon EOS 7D") or \
		 (image_data.get('model_exif') == "Canon EOS 7D Mark II") or \
		 (image_data.get('model_exif') == "Canon PowerShot G1 X Mark II") or \
		 (image_data.get('model_exif') == "Canon PowerShot G9") or \
		 (image_data.get('model_exif') == "Canon EOS M") or \
		 (image_data.get('model_exif') == "iPhone 6")):

		# In these cases the number is after the last underscore.
#		print("Grabbing file number from file name")
		filenumber = image_data.get('file_name').rsplit('_', 1)[1]

	# The Galaxy S7 creates a file number in the file name only if there are multiple
	# images in that second or in burst mode. The file numbers
	# will either be _NNN.EXT or (N).EXT depending on mode. Look for both.
	# Note that they are optional, and usually not there.
	if (filenumber == "None") and (image_data.get('model_exif') == "SM-G930V"):
		filenumber = get_filenumber_s7(metadata, image_data, filenumber)

	if filenumber != "None":
		# Make sure the filenumber is truncated or expanded to 4 digits

		# First pad out to 4 chars with leading 0's
		filenumber = filenumber.zfill(4)

		# And then take the last 4 chars in case it was too long
		filenumber = filenumber[-4:]

		image_data["filenumber"] = filenumber
		return 0

	return 1

# Create the full destination directory path where the output file will me moved to
# The path format is: /optional/path/set/by/user/YYYYMMDD/
#
# /optional/path/set/by/user/ is set by a the optional --parentdir option
# YYMMDD/ is optionally turned off by the --nosubdir option
#
def create_dirpath(image_data, parentdir, nosubdir):
	dest_dir = ""

	if parentdir:
		dest_dir = parentdir + "/"

	if nosubdir == False:
		dest_dir = dest_dir \
			+ "%.2d" % (image_data.get('year')) \
			+ "%.2d" % (image_data.get('month')) \
			+ "%.2d" % (image_data.get('day')) \
			+ "/"

	return dest_dir

# Create the name of the destination file. The format is:
#
# YYYYMMDD_HH_MM_SS_CAMERAMODEL_FILENUMBER.EXT
#
def create_dest_file_name(image_data):
	dest_file = "%.2d" % (image_data.get('year')) \
		+ "%.2d" % (image_data.get('month')) \
		+ "%.2d" % (image_data.get('day')) \
		+ "_" \
		+ "%.2d" % (image_data.get('hour')) \
		+ "_" \
		+ "%.2d" % (image_data.get('minute')) \
		+ "_" \
		+ "%.2d" % (image_data.get('second')) \
		+ "_" + image_data.get('model_mapped')

	if image_data.get('filenumber'):
		dest_file += "_" + image_data.get('filenumber')

	dest_file += "." + image_data.get('file_extension')

	return dest_file

# Do the actual file rename (unless preview is True)
#
def rename_file(dest_dir, dest_file, image_data, preview):
	if dest_dir:
#		print("Creating dest dir:", dest_dir)

		try:
			os.makedirs(dest_dir, exist_ok=True)

		except:
			print("Error: Could not create", dest_dir)
			return

	else:
		print("No sub folder to create")
		pass

	# Full path and name of destination file
	dest_full = dest_dir + dest_file
	src_full = image_data.get('fullfilepath')

	print("Moving", src_full, "to", dest_full)

	if preview == False:
#		# Get the src file's permissions
#		stat = os.stat(src_full)

		# Check if dest file exists
		if os.path.isfile(dest_full):
			print("ERROR: Destination file", dest_full, "Already exists. Skipping", src_full)
			return

		# if not, move
		try:
			shutil.move(src_full, dest_full)

		except:
			print("Error moving", src_full, "to", dest_full)
			return

#		# Reset file permissions to the src file's permissions
#		os.utime(dest_full, (stat.st_atime, stat.st_mtime))

	return

def main(argv):
	global verbose
	global exiftoolpath
	image_data = {}

	# Instantiate the parser
	parser = argparse.ArgumentParser(description='Rename images and videos from cameras')
	parser.add_argument('--exiftool', nargs='?', help='Exiftool path')
	parser.add_argument('--skewd', type=int, nargs='?', default=0, help='Set skew days')
	parser.add_argument('--skewm', type=int, nargs='?', default=0, help='Set skew minutes')
	parser.add_argument('--skewh', type=int, nargs='?', default=0, help='Set skew hours')
	parser.add_argument('--skews', type=int, nargs='?', default=0, help='Set skew seconds')
	parser.add_argument('--camera', nargs='?', help='Set camera name')
	parser.add_argument('-v', action='store_true', help='Be Verbose')
	parser.add_argument('-p', action='store_true', help='Preview actions only')
	parser.add_argument('--parentdir', nargs='?', help='Destination directory before dated subdirectory')
	parser.add_argument('--nosubdir', action='store_true', help='Do not create dated subdirectory')
	parser.add_argument('-f', required=True, nargs='+', help='Files to rename')
	args = parser.parse_args()

	verbose = args.v

	if verbose:
		print("Argument Values:")
		print(args.skewd)
		print(args.skewm)
		print(args.skewh)
		print(args.skews)
		print(args.camera)
		print(args.v)
		print(args.p)
		print(args.parentdir)
		print(args.nosubdir)
#		print(args.f)

	# Sorting the args list because in some cases info is grabbed from sidecar files
	# and we want those next to the video/image file to make things easier to track.
	# Most of the time the args list is already sorted, but this is pretty cheap.
	#
	# TODO - this probably isn't actually necessary
	args.f.sort()

#	print("Fetching all exifdata from %d files..." % len(args.f))

	if args.exiftool:
		exiftoolpath = args.exiftool

	# Fetch all metadata for each image. This could take a few on large data sets.
	with exiftool.ExifTool(exiftoolpath + "exiftool") as et:
		metadata_all = et.get_metadata_batch(args.f)

#	print("Done")

	if verbose:
		# Print every field from every input image
		for metadata in metadata_all:
#			print(metadata)
			for key in metadata:
				print("   ", key, ":", metadata[key], "<--")

	# Iterate and process each image, grabbing the bits of info we need
	# to do the rename
	for metadata in metadata_all:
		# Clear out the previous image data dictionary
		image_data.clear()

#		print("Input File:", metadata.get("SourceFile"))

		# Full path to original file with folder information
		image_data['fullfilepath'] = metadata.get("SourceFile")

		# Get the base file name before the extension
		image_data['file_name'] = os.path.splitext(metadata.get("File:FileName"))[0]
#		print("filename:", image_data['file_name'])
		if not image_data['file_name']:
			v_print("No file name found. Skipping.")
			continue

		# Get the file extension for the file name
		image_data['file_extension'] = os.path.splitext(metadata.get("File:FileName"))[1][1:]
#		print("ext:", image_data['file_extension'])
		if not image_data['file_extension']:
			v_print("No file extension found. Skipping.")
			continue

		if image_data['file_extension'].upper() == "AVI":
			# Skip the G9 AVI files. Data grabbed from the THM
			# TODO - check if the AVI files are really from the G9
			v_print("Skipping AVI")
			continue

		# Convert to a usable camera model name
		if args.camera:
			image_data['model_mapped'] = args.camera
		else:
			get_camera_model(metadata, image_data)

		if image_data.get('model_mapped').upper() == "UNKNOWN":
			print("Unknown Camera Model", image_data.get("model_exif"), ". Skipping: ", metadata.get("SourceFile"))
			continue

		# Skip the 5DM2 and 7D MOV files. Data grabbed from the THM because it is
		# missing from the MOV files
		# TODO - update this logic a bit
		if (image_data['file_extension'].upper() == "MOV") and \
			((image_data['model_exif'] == "Canon EOS 5D Mark II") or \
			 (image_data['model_exif'] == "Canon EOS 7D")):
			print(metadata["SourceFile"], "- Skipping. Getting data from THM")
			continue

		if get_date(metadata, image_data) != 0:
			print("Could not get date. Skipping")
			continue

		if get_filenumber(metadata, image_data) != 0:
			print("Could not get file number. Non fatal.")

		add_skew(image_data, metadata, args.skewd, args.skewh, args.skewm, args.skews)

#		print(image_data)

		dest_dir = create_dirpath(image_data, args.parentdir, args.nosubdir)
		dest_file = create_dest_file_name(image_data)

#		print("Destination Dir:", dest_dir)
#		print("Destination file:", dest_file)

		# The S7 and S4 have timestamps set to GMT in the video exif. If we didn't add a skew
		# to compensate, skip file
		if (image_data.get('file_extension').upper() == "MP4") and \
		   ((image_data.get('model_mapped') == "S7") or (image_data.get('model_mapped') == "S4")) and \
		   (skew_set(args.skewd, args.skewh, args.skewm, args.skews) == False):
			print("Skipping file. Video from phone that usually requires a skew value for correct time.")
			continue

		# If this is a THM file and we skipped the MOV rename the associated
		# MOV files as well (5DM2, G9 AVIs, etc)
		if image_data.get('file_extension').upper() == "THM":
			if (image_data.get('model_exif') == "Canon EOS 5D Mark II") or \
			(image_data.get('model_exif') == "Canon EOS 7D"):
#				print("SPECIAL CASE 1")

				tmp_image_data = deepcopy(image_data)
				tmp_image_data['file_extension'] = "MOV"

				tmp_src_file = tmp_image_data.get('fullfilepath')[:-3]
				tmp_src_file += "MOV"
				tmp_image_data['fullfilepath'] = tmp_src_file;

				tmp_dest_file = create_dest_file_name(tmp_image_data)
				rename_file(dest_dir, tmp_dest_file, tmp_image_data, args.p)

			else:  # TODO - check/verify this is for the G9 AVI
#				print("SPECIAL CASE 2")

				tmp_image_data = deepcopy(image_data)
				tmp_image_data['file_extension'] = "AVI"

				tmp_src_file = tmp_image_data.get('fullfilepath')[:-3]
				tmp_src_file += "AVI"
				tmp_image_data['fullfilepath'] = tmp_src_file;

				tmp_dest_file = create_dest_file_name(tmp_image_data)
				rename_file(dest_dir, tmp_dest_file, tmp_image_data, args.p)				

		rename_file(dest_dir, dest_file, image_data, args.p)

if __name__ == "__main__":
	main(sys.argv)

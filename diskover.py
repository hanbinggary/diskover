#!/usr/bin/env python
# -*- coding: utf-8 -*-
# diskover - Elasticsearch file system crawler
# https://github.com/shirosaidev/diskover

from random import randint
from datetime import datetime
from elasticsearch import Elasticsearch, helpers, RequestsHttpConnection
try:
	from os import scandir
except ImportError:
	from scandir import scandir
import os
import sys
from sys import platform
import subprocess
import time
import argparse
try:
	import queue as Queue
except ImportError:
	import Queue
import threading
try:
	import configparser as ConfigParser
except ImportError:
	import ConfigParser
import hashlib
import logging

IS_PY3 = sys.version_info >= (3, 0)

if IS_PY3:
	unicode = str

IS_WIN = platform == "win32"

if not IS_WIN:
	import pwd
	import grp

if IS_WIN:
	import win32security

DISKOVER_VERSION = '1.1.0'

def printBanner():
	"""This is the print banner function.
	It prints a random banner.
	"""
	b = randint(1,3)
	if b == 1:
		banner = """\033[35m
  ________  .__        __
  \______ \ |__| _____|  | _________  __ ___________
   |    |  \|  |/  ___/  |/ /  _ \  \/ // __ \_  __ \\ /)___(\\
   |    `   \  |\___ \|    <  <_> )   /\  ___/|  | \/ (='.'=)
  /_______  /__/____  >__|_ \____/ \_/  \___  >__|   (\\")_(\\")
          \/        \/     \/   v%s     \/
                      https://github.com/shirosaidev/diskover\033[0m
""" % DISKOVER_VERSION
	elif b == 2:
		banner = """\033[35m
   ___       ___       ___       ___       ___       ___       ___       ___
  /\  \     /\  \     /\  \     /\__\     /\  \     /\__\     /\  \     /\  \\
 /::\  \   _\:\  \   /::\  \   /:/ _/_   /::\  \   /:/ _/_   /::\  \   /::\  \\
/:/\:\__\ /\/::\__\ /\:\:\__\ /::-"\__\ /:/\:\__\ |::L/\__\ /::\:\__\ /::\:\__\\
\:\/:/  / \::/\/__/ \:\:\/__/ \;:;-",-" \:\/:/  / |::::/  / \:\:\/  / \;:::/  /
 \::/  /   \:\__\    \::/  /   |:|  |    \::/  /   L;;/__/   \:\/  /   |:\/__/
  \/__/     \/__/     \/__/     \|__|     \/__/    v%s    \/__/     \|__|
                                      https://github.com/shirosaidev/diskover\033[0m
""" % DISKOVER_VERSION
	elif b == 3:
		banner = """\033[35m
    _/_/_/    _/            _/
   _/    _/        _/_/_/  _/  _/      _/_/    _/      _/    _/_/    _/  _/_/
  _/    _/  _/  _/_/      _/_/      _/    _/  _/      _/  _/_/_/_/  _/_/
 _/    _/  _/      _/_/  _/  _/    _/    _/    _/  _/    _/        _/
_/_/_/    _/  _/_/_/    _/    _/    _/_/        _/ v%s  _/_/_/  _/
                              https://github.com/shirosaidev/diskover\033[0m
""" % DISKOVER_VERSION
	sys.stdout.write(banner)
	sys.stdout.write('\n')
	sys.stdout.flush()
	return

def printProgressBar(iteration, total, prefix='', suffix=''):
	"""This is the create terminal progress bar function.
	It shows progress of the queue.
	"""
	decimals = 0
	bar_length = 40
	str_format = "{0:." + str(decimals) + "f}"
	percents = str_format.format(100 * (iteration / float(total)))
	filled_length = int(round(bar_length * iteration / float(total)))
	bar = '#' * filled_length + '.' * (bar_length - filled_length)
	sys.stdout.write('\r\033[44m\033[37m%s [%s%s]\033[0m |%s| %s' \
		% (prefix, percents, '%', bar, suffix))
	sys.stdout.flush()
	return

def loadConfig():
	"""This is the load config function.
	It checks for config file and loads in
	the config settings.
	"""
	config = ConfigParser.RawConfigParser()
	dir_path = os.path.dirname(os.path.realpath(__file__))
	configfile = '%s/diskover.cfg'% dir_path
	# Check for config file
	if not os.path.isfile(configfile):
		sys.exit('Config file not found')
	config.read(configfile)
	try:
		d = config.get('excluded_dirs', 'dirs')
		EXCLUDED_DIRS = d.split(',')
	except:
		EXCLUDED_DIRS = ''
		pass
	try:
		f = config.get('excluded_files', 'files')
		EXCLUDED_FILES = f.split(',')
	except:
		EXCLUDED_FILES = ''
		pass
	try:
		AWS = config.get('elasticsearch', 'aws')
	except:
		AWS = 'False'
		pass
	ES_HOST = config.get('elasticsearch', 'host')
	ES_PORT = int(config.get('elasticsearch', 'port'))
	try:
		ES_USER = config.get('elasticsearch', 'user')
	except:
		ES_USER = ''
		pass
	try:
		ES_PASSWORD = config.get('elasticsearch', 'password')
	except:
		ES_PASSWORD = ''
		pass
	try:
		INDEXNAME = config.get('elasticsearch', 'indexname')
	except:
		INDEXNAME = ''
		pass

	return AWS, ES_HOST, ES_PORT, ES_USER, ES_PASSWORD, INDEXNAME, \
		EXCLUDED_DIRS, EXCLUDED_FILES

def parseCLIArgs(INDEXNAME):
	"""This is the parse CLI arguments function.
	It parses command line arguments.
	"""
	parser = argparse.ArgumentParser()
	parser.add_argument("-d", "--topdir", default=".", type=str,
						help="Directory to start crawling from (default: .)")
	parser.add_argument("-m", "--mtime", default=30, type=int,
						help="Minimum days ago for modified time (default: 30)")
	parser.add_argument("-s", "--minsize", default=5, type=int,
						help="Minimum file size in MB (default: 5)")
	parser.add_argument("-t", "--threads", default=2, type=int,
						help="Number of threads to use (default: 2)")
	parser.add_argument("-i", "--index", type=str,
						help="Elasticsearch index name (default: from config)")
	parser.add_argument("-n", "--nodelete", action="store_true",
						help="Do not delete existing index (default: delete index)")
	parser.add_argument("--tagdupes", action="store_true",
						help="Tags duplicate files (default: don't tag)")
	parser.add_argument("--version", action="store_true",
						help="Prints version and exits")
	parser.add_argument("-v", "--verbose", action="store_true",
						help="Increase output verbosity")
	parser.add_argument("--debug", action="store_true",
						help="Debug message output")
	args = parser.parse_args()

	# use index name from command line instead of config file
	if args.index:
		INDEXNAME = args.index
	# check index name
	if INDEXNAME == "diskover" or INDEXNAME.split('-')[0] != "diskover":
		print('Please name your index: diskover-<string>')
		sys.exit(0)

	return args.topdir, args.mtime, args.minsize, args.threads, INDEXNAME, \
		args.nodelete, args.tagdupes, args.version, args.verbose, args.debug

def crawlDirectories(TOPDIR, EXCLUDED_DIRS, DIRECTORY_QUEUE, LOGGER, VERBOSE, DEBUG):
	"""This is the walk directory tree function.
	It crawls the tree top-down using find command
	and adds directories to the Queue.
	Ignores directories that are empty and in
	'EXCLUDED_DIRS'.
	"""
	global total_num_dirs
	cmd = ['find', TOPDIR, '-type', 'd', '-and', '-not', '-empty']
	for i in EXCLUDED_DIRS:
		cmd.append('-and')
		cmd.append('-not')
		cmd.append('-path')
		cmd.append('*%s*' % i)
	if VERBOSE or DEBUG:
		LOGGER.info('Finding directories to crawl')
	if IS_WIN:
		p = subprocess.Popen(cmd,shell=True,stdin=subprocess.PIPE,
						stdout=subprocess.PIPE,stderr=subprocess.PIPE)
	else:
		p = subprocess.Popen(cmd,shell=False,stdin=subprocess.PIPE,
						stdout=subprocess.PIPE,stderr=subprocess.PIPE)
	for line in p.stdout:
		# check python version and remove any newline chars
		if IS_PY3:
			directory = line.decode().rstrip('\r\n').encode('utf-8')
		else:
			directory = line.rstrip('\r\n')
		if VERBOSE or DEBUG:
			LOGGER.info('Queuing directory: %s', directory)
		# add item to queue (directory)
		DIRECTORY_QUEUE.put(directory)
		total_num_dirs += 1
	return

def crawlFiles(path, DATEEPOCH, DAYSOLD, MINSIZE, EXCLUDED_FILES, LOGGER):
	"""This is the list directory function.
	It crawls for files using scandir.
	Ignores files smaller than 'MINSIZE' MB, newer
	than 'DAYSOLD' old and in 'EXCLUDED_FILES'.
	Tries to reduce the amount of stat calls to the fs
	to help speed up crawl times.
	"""
	global total_num_files
	filelist = []
	# try to crawl files in directory
	try:
		if IS_WIN:
			path = str(path.decode())
		# Crawl files in the directory
		for entry in scandir(path):
			# check if file is in excluded list and regular file and don't follow symlinks
			if not entry.name in EXCLUDED_FILES and entry.is_file(follow_symlinks=False):
				# get absolute path (parent of file)
				abspath = os.path.abspath(path)
				# get full path to file
				filename_fullpath = os.path.join(abspath, entry.name)
				# try to index file
				try:
					size = os.path.getsize(filename_fullpath)
					# Convert bytes to MB
					size_mb = size / 1024 / 1024
					# Skip files smaller than x MB and skip empty files
					if size_mb >= MINSIZE and size > 0:
						# Get file modified time
						mtime_unix = os.path.getmtime(filename_fullpath)
						mtime_utc = datetime.utcfromtimestamp(mtime_unix).strftime('%Y-%m-%dT%H:%M:%S')
						# Convert time in days to seconds
						time_sec = DAYSOLD * 86400
						file_mtime_sec = DATEEPOCH - mtime_unix
						# Only process files modified at least x days ago
						if file_mtime_sec >= time_sec:
							# get file extension
							extension = os.path.splitext(filename_fullpath)[1][1:].strip().lower()
							# get access time
							atime_unix = os.path.getatime(filename_fullpath)
							atime_utc = datetime.utcfromtimestamp(atime_unix).strftime('%Y-%m-%dT%H:%M:%S')
							# get change time
							ctime_unix = os.path.getctime(filename_fullpath)
							ctime_utc = datetime.utcfromtimestamp(ctime_unix).strftime('%Y-%m-%dT%H:%M:%S')
							if IS_WIN:
								sd = win32security.GetFileSecurity(filename_fullpath, win32security.OWNER_SECURITY_INFORMATION)
								owner_sid = sd.GetSecurityDescriptorOwner()
								owner, domain, type = win32security.LookupAccountSid(None, owner_sid)
								# placeholders for windows
								group = "0"
								inode = "0"
							else:
								# get user id of owner
								uid = os.stat(filename_fullpath).st_uid
								# try to get owner user name
								try:
									owner = pwd.getpwuid(uid).pw_name.split('\\')
									# remove domain before owner
									if len(owner) == 2:
										owner = owner[1]
									else:
										owner = owner[0]
								# if we can't find the owner's user name, use the uid number
								except KeyError:
									owner = uid
								# get group id
								gid = os.stat(filename_fullpath).st_gid
								# try to get group name
								try:
									group = grp.getgrgid(gid).gr_name.split('\\')
									# remove domain before group
									if len(group) == 2:
										group = group[1]
									else:
										group = group[0]
								# if we can't find the group name, use the gid number
								except KeyError:
									group = gid
								# get inode number
								inode = os.stat(filename_fullpath).st_ino
							# get number of hardlinks
							hardlinks = os.stat(filename_fullpath).st_nlink
							if IS_WIN:
								name = entry.name
							else:
								name = entry.name.decode('utf-8')
								extension = extension.decode('utf-8')
								filename_fullpath = filename_fullpath.decode('utf-8')
								abspath = abspath.decode('utf-8')
							# create md5 hash of file using metadata
							filestring = unicode(name) + str(size) + str(mtime_unix)
							filehash = hashlib.md5(filestring.encode('utf-8')).hexdigest()
							# get time
							indextime_utc = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
							# create file metadata dictionary
							filemeta_dict = {
								"filename": "%s" % name,
								"extension": "%s" % extension,
								"path_full": "%s" % filename_fullpath,
								"path_parent": "%s" % abspath,
								"filesize": size,
								"owner": "%s" % owner,
								"group": "%s" % group,
								"last_modified": "%s" % mtime_utc,
								"last_access": "%s" % atime_utc,
								"last_change": "%s" % ctime_utc,
								"hardlinks": hardlinks,
								"inode": inode,
								"filehash": "%s" % filehash,
								"tag": "untagged",
								'is_dupe': "false",
								"indexing_date": "%s" % indextime_utc
								}
							# add file metadata dictionary to filelist list
							filelist.append(filemeta_dict)
							total_num_files += 1
				except Exception:
					LOGGER.error('Failed to index file', exc_info=True)
		return filelist
	except Exception:
		LOGGER.error('Failed to crawl directory', exc_info=True)
	return

def workerSetup(DIRECTORY_QUEUE, NUM_THREADS, ES, INDEXNAME, DATEEPOCH, \
		DAYSOLD, MINSIZE, EXCLUDED_FILES, LOGGER, VERBOSE, DEBUG):
	"""This is the worker setup function.
	It sets up the worker threads to process
	the directory list Queue.
	"""
	for i in range(NUM_THREADS):
		worker = threading.Thread(target=processDirectoryWorker, \
			args=(i, DIRECTORY_QUEUE, ES, INDEXNAME, DATEEPOCH, DAYSOLD, \
				MINSIZE, EXCLUDED_FILES, LOGGER, VERBOSE, DEBUG,))
		worker.setDaemon(True)
		worker.start()
	return

def processDirectoryWorker(threadnum, DIRECTORY_QUEUE, ES, INDEXNAME, DATEEPOCH, \
		DAYSOLD, MINSIZE, EXCLUDED_FILES, LOGGER, VERBOSE, DEBUG):
	"""This is the worker thread function.
	It processes items in the Queue one after another.
	These daemon threads go into an infinite loop,
	and only exit when the main thread ends and
	there are no more paths.
	"""
	global total_num_dirs
	filelist = []
	while True:
		if VERBOSE or DEBUG:
			LOGGER.info('[thread-%s]: Looking for the next directory', threadnum)
		# get an item (directory) from the queue
		path = DIRECTORY_QUEUE.get()
		if VERBOSE or DEBUG:
			LOGGER.info('[thread-%s]: Crawling: %s', threadnum, path)
		# crawl the files in the directory
		filelist = crawlFiles(path, DATEEPOCH, DAYSOLD, MINSIZE, \
			EXCLUDED_FILES, LOGGER)
		if filelist:
			# add filelist to ES index
			indexAdd(threadnum, ES, INDEXNAME, filelist, LOGGER, VERBOSE, DEBUG)
		# print progress bar
		dircount = total_num_dirs - DIRECTORY_QUEUE.qsize()
		if dircount > 0 and not VERBOSE and not DEBUG:
			printProgressBar(dircount, total_num_dirs, 'Crawling:', '%s/%s' \
				% (dircount, total_num_dirs))
		# task is done
		DIRECTORY_QUEUE.task_done()
	return

def elasticsearchConnect(AWS, ES_HOST, ES_PORT, ES_USER, ES_PASSWORD, LOGGER):
	"""This is the ES function.
	It creates the connection to Elasticsearch
	and checks if it can connect.
	"""
	# Check if we are using AWS ES
	if AWS == 'True':
		ES = Elasticsearch(hosts=[{'host': ES_HOST, 'port': ES_PORT}], \
			use_ssl=True, verify_certs=True, connection_class=RequestsHttpConnection)
	# Local connection to ES
	else:
		ES = Elasticsearch(hosts=[{'host': ES_HOST, 'port': ES_PORT}], \
			http_auth=(ES_USER, ES_PASSWORD))
	LOGGER.info('Connecting to Elasticsearch')
	# Ping check ES
	if not ES.ping():
		LOGGER.error('Unable to connect to Elasticsearch, check diskover.cfg and ES')
		sys.exit(1)
	return ES

def indexCreate(ES, INDEXNAME, NODELETE, LOGGER):
	"""This is the ES index create function.
	It checks for existing index and deletes if
	there is one with same name. It also creates
	the new index and sets up mappings.
	"""
	LOGGER.info('Checking for ES index: %s', INDEXNAME)
	# check for existing es index
	if ES.indices.exists(index=INDEXNAME):
		# check if nodelete cli argument and don't delete existing index
		if NODELETE:
			LOGGER.warning('ES index exists, NOT deleting')
			return
		# delete existing index
		else:
			LOGGER.warning('ES index exists, deleting')
			ES.indices.delete(index=INDEXNAME, ignore=[400, 404])
	# set up es index mappings and create new index
	mappings = {
		"mappings": {
			"file": {
				"properties": {
					"filename": {
						"type": "keyword"
					},
					"extension": {
						"type": "keyword"
					},
					"path_full": {
						"type": "keyword"
					},
					"path_parent": {
						"type": "keyword"
					},
					"filesize": {
						"type": "long"
					},
					"owner": {
						"type": "keyword"
					},
					"group": {
						"type": "keyword"
					},
					"last_modified": {
						"type": "date"
					},
					"last_access": {
						"type": "date"
					},
					"last_change": {
						"type": "date"
					},
					"hardlinks": {
						"type": "integer"
					},
					"inode": {
						"type": "long"
					},
					"filehash": {
						"type": "keyword"
					},
					"tag": {
						"type": "keyword"
					},
					"is_dupe": {
						"type": "boolean"
					},
					"indexing_date": {
						"type": "date"
					}
				}
			}
		}
	}
	LOGGER.info('Creating ES index')
	ES.indices.create(index=INDEXNAME, body=mappings)
	return

def indexAdd(threadnum, ES, INDEXNAME, filelist, LOGGER, VERBOSE, DEBUG):
	"""This is the ES index add function.
	It bulk adds data from worker's crawl
	results into ES.
	"""
	if VERBOSE or DEBUG:
		LOGGER.info('[thread-%s]: Bulk adding to ES index', threadnum)
	# bulk load data to Elasticsearch index
	helpers.bulk(ES, filelist, index=INDEXNAME, doc_type='file')
	return

def indexUpdate(threadnum, ES, INDEXNAME, filelist, LOGGER, VERBOSE, DEBUG):
	"""This is the ES index update function.
	It updates data in ES.
	"""
	data = [];
	if VERBOSE or DEBUG:
		LOGGER.info('[thread-%s]: Bulk updating data in ES index', threadnum)
	# bulk update data in Elasticsearch index
	for file in filelist:
		id = file['_id']
		d = {
	    '_op_type': 'update',
	    '_index': INDEXNAME,
	    '_type': 'file',
	    '_id': id,
	    'doc': {'is_dupe': 'true'}
		}
		data.append(d)
	helpers.bulk(ES, data, index=INDEXNAME, doc_type='file')
	return

def tagDupes(ES, INDEXNAME, NODELETE, LOGGER, VERBOSE, DEBUG):
	"""This is the duplicate file tagger.
	It tags dupe files (same filehash) in an existing index.
	"""
	# search ES for duplicate files
	dupes_list = dupesFinder(ES, INDEXNAME, LOGGER)
	# update existing index and tag dupe files is_dupe field
	indexUpdate(0, ES, INDEXNAME, dupes_list, LOGGER, VERBOSE, DEBUG)
	return

def dupesFinder(ES, INDEXNAME, LOGGER):
	"""This is the duplicate file finder function.
	It searches Elasticsearch for files that have the same filehash
	and returns a list of those dupes.
	"""
	global total_num_files
	dupes_list = []
	dupe_count = 0
	data = {
	"size": 0,
	"aggs": {
	  "duplicateCount": {
	    "terms": {
	    "field": "filehash",
	      "min_doc_count": 2,
		  "size": 1000
	    },
	    "aggs": {
	      "duplicateDocuments": {
	        "top_hits": {
			"size": 1000
			}
	      }
	    }
	  }
	}
	}
	LOGGER.info('Refreshing ES index')
	ES.indices.refresh(index=INDEXNAME)
	LOGGER.info('Searching index for duplicate files')
	res = ES.search(index=INDEXNAME, body=data)
	for hit in res['aggregations']['duplicateCount']['buckets']:
		for hit in hit['duplicateDocuments']['hits']['hits']:
			dupes_list.append(hit)
			dupe_count += 1
	total_num_files = dupe_count
	LOGGER.info('Found: %s dupes', dupe_count)
	return dupes_list

def printStats(DATEEPOCH, LOGGER, stats_type='indexing'):
	"""This is the print stats function
	It outputs stats at the end of runtime.
	"""
	elapsedtime = time.time() - DATEEPOCH
	sys.stdout.flush()
	if stats_type is 'indexing':
		LOGGER.info('Directories Crawled: %s', total_num_dirs)
		LOGGER.info('Files Indexed: %s', total_num_files)
	if stats_type is 'updating':
		LOGGER.info('Files updated: %s', total_num_files)
	LOGGER.info('Elapsed time: %s', elapsedtime)
	return

def main():
	global total_num_files
	global total_num_dirs

	# initialize file and directory counts
	total_num_files = 0
	total_num_dirs = 0

	# Date calculation seconds since epoch
	DATEEPOCH = time.time()

	# print random banner
	printBanner()

	# load config file
	AWS, ES_HOST, ES_PORT, ES_USER, ES_PASSWORD, INDEXNAME, \
		EXCLUDED_DIRS, EXCLUDED_FILES = loadConfig()

	# parse cli arguments
	TOPDIR, DAYSOLD, MINSIZE, NUM_THREADS, INDEXNAME, NODELETE, \
		TAGDUPES, VERSION, VERBOSE, DEBUG = parseCLIArgs(INDEXNAME)

	# check --version flag and exit
	if VERSION:
		print('diskover v%s' % DISKOVER_VERSION)
		sys.exit(0)

	if not IS_WIN:
		# check we are root
		if os.geteuid():
			print('Please run as root')
			sys.exit(1)

	# set up logging
	es_logger = logging.getLogger('elasticsearch')
	es_logger.setLevel(logging.WARNING)
	logging.addLevelName( logging.INFO, "\033[1;32m%s\033[1;0m" \
		% logging.getLevelName(logging.INFO))
	logging.addLevelName( logging.WARNING, "\033[1;31m%s\033[1;0m" \
		% logging.getLevelName(logging.WARNING))
	logging.addLevelName( logging.ERROR, "\033[1;41m%s\033[1;0m" \
		% logging.getLevelName(logging.ERROR))
	logging.addLevelName( logging.DEBUG, "\033[1;33m%s\033[1;0m" \
		% logging.getLevelName(logging.DEBUG))
	logFormatter = '%(asctime)s [%(levelname)s][%(name)s] %(message)s'
	loglevel = logging.INFO
	if VERBOSE:
		loglevel = logging.INFO
		es_logger.setLevel(logging.INFO)
	if DEBUG:
		loglevel = logging.DEBUG
		es_logger.setLevel(logging.DEBUG)
	logging.basicConfig(format=logFormatter, level=loglevel)
	LOGGER = logging.getLogger('diskover')

	# connect to Elasticsearch
	ES = elasticsearchConnect(AWS, ES_HOST, ES_PORT, ES_USER, ES_PASSWORD, LOGGER)

	# create Elasticsearch index
	indexCreate(ES, INDEXNAME, NODELETE, LOGGER)

	# Set up directory queue
	DIRECTORY_QUEUE = Queue.Queue()

	try:
		# Set up worker threads
		workerSetup(DIRECTORY_QUEUE, NUM_THREADS, ES, INDEXNAME, DATEEPOCH, \
			DAYSOLD, MINSIZE, EXCLUDED_FILES, LOGGER, VERBOSE, DEBUG)
		# walk directory tree and start crawling
		crawlDirectories(TOPDIR, EXCLUDED_DIRS, DIRECTORY_QUEUE, LOGGER, VERBOSE, DEBUG)
		# wait for all threads to finish
		for i in range(NUM_THREADS):
			DIRECTORY_QUEUE.join()
		sys.stdout.write('\n')
		sys.stdout.flush()
		LOGGER.info('Finished crawling')
		printStats(DATEEPOCH, LOGGER)
		# tag duplicate files if cli argument
		if TAGDUPES:
			timenow = time.time()
			tagDupes(ES, INDEXNAME, NODELETE, LOGGER, VERBOSE, DEBUG)
			printStats(timenow, LOGGER, stats_type='updating')
		# exit, we're all done!
		sys.exit(0)
	except KeyboardInterrupt:
		print('\nCtrl-c keyboard interrupt received, exiting')
		printStats(DATEEPOCH, LOGGER)
		sys.exit(0)

if __name__ == "__main__":
	main()

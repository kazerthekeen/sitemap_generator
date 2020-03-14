#! /usr/bin/env python3
"""
    Copyright (C) 2007-2009 Vladimir Toncar
    Copyright (C) 2018-2020 Bernhard Ehlers

    Contributors:
        Redirect handling by Pavel "ShadoW" Dvorak

    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

"""

import sys
import getopt
import string
import time
import urllib.parse
import xml.sax.saxutils
from datetime import datetime
from html.parser import HTMLParser
import requests
from reppy.robots import Robots


helpText = """sitemap_gen.py version 1.2.5 (2020-03-14)

This script crawls a web site from a given starting URL and generates
a Sitemap file in the format that is accepted by Google. The crawler
does not follow links to other web sites. It also respects the 'nofollow'
tags and will not crawl into directories disallowed in the robots.txt file.

Command line syntax:

python3 sitemap_gen.py <options> <starting URL>

Available options:
-h         --help                Print this text and exit

-b <ext>   --block <ext>         Exclude URLs with the given extension;
                                 <ext> must be without the leading dot.
                                 The comparison is case insensitive, so
                                 for example DOC and doc are treated
                                 the same. You can use this option several
                                 times to block several extensions.

-c <value> --changefreq <value>  Set the change frequency. The given value
                                 is used in all sitemap entries (maybe a
                                 future version of this script will change
                                 that). The allowed values are: always,
                                 hourly, daily, weekly, monthly, yearly,
                                 never.

-p <prio>  --priority <prio>     Set the priority. The value must be from
                                 the interval between 0.0 and 1.0. The value
                                 will be used in all sitemap entries.

-m <value> --max-urls <value>    Set the maximum number of URLs to be crawled.
                                 The default value is 1000 and the largest
                                 value that you can set is 50000 (the script
                                 generates only a single sitemap file).

-r <value> --ratelimit <value>   Set a crawl rate limit [requests / second],
                                 zero (the default) results in no crawl rate
                                 limitation.

-o <file>  --output-file <file>  Set the name of the geneated sitemap file.
                                 The default file name is sitemap.xml.

Usage example:
python3 sitemap_gen.py -b doc -b bmp -o test_sitemap.xml http://www.your-site-name.com/index.html

For more information, visit http://toncar.cz/opensource/sitemap_gen.html

"""

allowedChangefreq = ["always", "hourly", "daily", "weekly", \
                     "monthly", "yearly", "never"]

class RateLimit:
    """ rate limit requests """

    def __init__(self, rate):
        if rate <= 0.0:
            self.interval_ns = None
        else:
            self.interval_ns = round(1e9 / rate)
            self.req_time_ns = time.monotonic_ns() - self.interval_ns

    def sleep(self):
        if self.interval_ns:
            self.req_time_ns += self.interval_ns
            cur_time_ns = time.monotonic_ns()
            sleep_time = (self.req_time_ns - cur_time_ns) / 1e9
            if sleep_time > 0.0:
                time.sleep(sleep_time)
            else:
                self.req_time_ns = cur_time_ns

class HTMLLoad:
    """ load http(s) page """

    def __init__(self, ratelimit=None):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'sitemap_gen/1.0'})
        if not ratelimit:
            ratelimit = 0.0
        self.ratelimit = RateLimit(ratelimit)
        self.page = None
        self.status = 0
        self.date = None
        self.redirect = None

    def _handle_redirect(self, resp):
        # taken from urllib.request source code
        newurl = resp.headers.get("location")
        if not newurl:
            raise requests.exceptions.HTTPError(
                "%s No new location in redirection for url: %s" %
                (resp.status_code, resp.url))
        urlparts = urllib.parse.urlparse(newurl)
        if urlparts.scheme not in ('http', 'https', 'ftp', ''):
            raise requests.exceptions.HTTPError(
                "%s Redirection to '%s' not allowed for url: %s" %
                (resp.status_code, newurl, resp.url))
        if not urlparts.path and urlparts.netloc:
            urlparts = urlparts._replace(path='/')
        newurl = urllib.parse.urlunparse(urlparts)
        # http.client.parse_headers() decodes as ISO-8859-1. Recover the
        # original bytes and percent-encode non-ASCII bytes, and any special
        # characters such as the space.
        newurl = urllib.parse.quote(newurl, encoding="iso-8859-1",
                                    safe=string.punctuation)
        self.redirect = urllib.parse.urljoin(resp.url, newurl)

    def get(self, url, allow_redirects=False):
        self.page = None
        self.status = 0
        self.date = datetime.now()
        self.redirect = None

        self.ratelimit.sleep()
        try:
            resp = self.session.get(url, timeout=10,
                                    allow_redirects=allow_redirects)
            self.status = resp.status_code
            if resp.status_code in (301, 302, 303, 307):
                self._handle_redirect(resp)
            else:
                resp.raise_for_status()
            self.page = resp.content
            date = resp.headers.get('last-modified') or resp.headers.get('date')
            try:
                if date:
                    self.date = datetime.strptime(date,
                                                  '%a, %d %b %Y %H:%M:%S %Z')
            except ValueError:
                pass

        except requests.exceptions.RequestException as detail:
            print("%s. Skipping..." % (detail))

        return self.page
#end class


def joinUrls(baseUrl, newUrl):
    helpUrl, _ = urllib.parse.urldefrag(newUrl)
    return urllib.parse.urljoin(baseUrl, helpUrl)
#end def


def getRobotParser(loader, startUrl):
    robotUrl = urllib.parse.urljoin(startUrl, "/robots.txt")
    page = loader.get(robotUrl, allow_redirects=True)

    if page is None:
        print("Could not read ROBOTS.TXT at: " + robotUrl)
        return None
    #end if

    rp = Robots.parse(robotUrl, page)
    print("Found ROBOTS.TXT at: " + robotUrl)
    return rp
#end def

EMPTY = []

class MyHTMLParser(HTMLParser):

    def __init__(self, pageMap, redirects, baseUrl, maxUrls, blockExtensions, robotParser):
        HTMLParser.__init__(self)
        self.pageMap = pageMap
        self.redirects = redirects
        self.baseUrl = baseUrl
        self.server = urllib.parse.urlsplit(baseUrl)[1] # netloc in python 2.5
        self.maxUrls = maxUrls
        self.blockExtensions = tuple(blockExtensions)
        self.robotParser = robotParser
    #end def

    def hasBlockedExtension(self, url):
        p = urllib.parse.urlparse(url)
        path = p[2].upper() # path attribute
        return path.endswith(self.blockExtensions)
    #end def

    def handle_starttag(self, tag, attrs):
        if len(self.pageMap) >= self.maxUrls:
            return

        if tag.upper() == "BASE":
            if attrs[0][0].upper() == "HREF":
                self.baseUrl = joinUrls(self.baseUrl, attrs[0][1])
                print("BASE URL set to " + self.baseUrl)

        if tag.upper() == "A":
            #print("Attrs: " + str(attrs))
            url = ""
            # Let's scan the list of tag's attributes
            for attr in attrs:
                #print("  attr: " + str(attr))
                if (attr[0].upper() == "REL") and (attr[1].upper().find('NOFOLLOW') != -1):
                    # We have discovered a nofollow, so we won't continue
                    return
                elif (attr[0].upper() == "HREF") and (attr[1].upper().find('MAILTO:') == -1):
                    # We have discovered a link that is not a Mailto:
                    url = joinUrls(self.baseUrl, attr[1])
            #end for
            # if the url is empty, there was none in the list of attributes
            if url == "":
                return

            # Check if we want to follow the link
            if urllib.parse.urlsplit(url)[1] != self.server:
                return
            if self.hasBlockedExtension(url) or self.redirects.count(url) > 0:
                return
            if self.robotParser is not None and not self.robotParser.allowed(url, "sitemap_gen"):
                print("URL restricted by ROBOTS.TXT: " + url)
                return
            # It's OK to add url to the map and fetch it later
            if not url in self.pageMap:
                self.pageMap[url] = EMPTY
        #end if

    #end def
#end class

def getUrlToProcess(pageMap):
    for i in pageMap.keys():
        if pageMap[i] is EMPTY:
            return i
    return None

def parsePages(loader, startUrl, maxUrls, blockExtensions):
    pageMap = {}
    pageMap[startUrl] = EMPTY
    redirects = []

    robotParser = getRobotParser(loader, startUrl)
    server = urllib.parse.urlsplit(startUrl)[1]

    while True:
        url = getUrlToProcess(pageMap)
        if url is None:
            break
        print("  " + url)
        page = loader.get(url)
        if page is None:
            del pageMap[url]
        elif loader.redirect:
            newUrl, _ = urllib.parse.urldefrag(loader.redirect)
            print("Redirect -> " + newUrl)
            del pageMap[url]
            redirects.append(url)
            if urllib.parse.urlsplit(newUrl)[1] == server and \
               newUrl not in pageMap and newUrl not in redirects and \
               (robotParser is None or \
                robotParser.allowed(newUrl, "sitemap_gen")):
                pageMap[newUrl] = EMPTY
        else:
            pageMap[url] = loader.date
            parser = MyHTMLParser(pageMap, redirects, url, maxUrls, blockExtensions, robotParser)
            try:
                parser.feed(page.decode("utf-8", errors='strict'))
                parser.close()
            except UnicodeError:
                print("Failed decoding %s . Try to check if the page is valid." % (url))
    #end while

    return pageMap
#end def


def generateSitemapFile(pageMap, fileName, changefreq="", priority=0.0):
    fw = open(fileName, "wt")
    fw.write('''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n''')
    for i in sorted(pageMap.keys()):
        fw.write('<url>\n  <loc>%s</loc>\n' % (xml.sax.saxutils.escape(i)))
        if isinstance(pageMap[i], datetime):
            fw.write('  <lastmod>%4d-%02d-%02d</lastmod>\n' %
                     (pageMap[i].year, pageMap[i].month, pageMap[i].day))
        if changefreq != "":
            fw.write('  <changefreq>%s</changefreq>\n' % (changefreq))
        if priority > 0.0:
            fw.write('  <priority>%1.1f</priority>\n' % (priority))
        fw.write('</url>\n')
    #end for
    fw.write('</urlset>\n')
    fw.close()
#end def



def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:],\
                "hb:c:m:p:r:o:", \
                ["help", "block=", "changefreq=", "max-urls=", \
                 "priority=", "ratelimit=", "output-file="])
    except getopt.GetoptError:
        sys.stderr.write(helpText)
        return 1

    blockExtensions = []
    changefreq = ""
    priority = 0.0
    fileName = "sitemap.xml"
    maxUrls = 1000
    pageMap = {}
    ratelimit = None

    for opt, arg in opts:
        if opt in ("-h", "--help"):
            sys.stderr.write(helpText)
            return 1
        elif opt in ("-b", "--block"):
            blockExtensions.append("." + arg.upper())
        elif opt in ("-c", "--changefreq"):
            if arg in allowedChangefreq:
                changefreq = arg
            else:
                sys.stderr.write("Allowed changefreq values are:\n")
                for i in allowedChangefreq:
                    sys.stderr.write("  {}\n".format(i))
                return 1
        elif opt in ("-m", "--max-urls"):
            maxUrls = int(arg)
            if (maxUrls < 0) or (maxUrls > 50000):
                sys.stderr.write("The maximum number of URLs must be between 1 and 50000\n")
                return 1
        elif opt in ("-p", "--priority"):
            priority = float(arg)
            if (priority < 0.0) or (priority > 1.0):
                sys.stderr.write("Priority must be between 0.0 and 1.0\n")
                return 1
        elif opt in ("-r", "--ratelimit"):
            ratelimit = float(arg)
        elif opt in ("-o", "--output-file"):
            fileName = arg
            if fileName in ("", ".", ".."):
                sys.stderr.write("Please provide a sensible file name\n")
                return 1
        #end if

    if not args:
        sys.stderr.write("You must provide the starting URL.\nTry the -h option for help.\n")
        return 1

    # Start processing
    print("Crawling the site...")
    loader = HTMLLoad(ratelimit)
    pageMap = parsePages(loader, args[0], maxUrls, blockExtensions)
    print("Generating sitemap: %d URLs" % (len(pageMap)))
    generateSitemapFile(pageMap, fileName, changefreq, priority)
    print("Finished.")
    return 0
#end def

if __name__ == '__main__':
    try:
        status_code = main()
    except KeyboardInterrupt:
        status_code = 130
    sys.exit(status_code)

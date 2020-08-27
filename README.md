# Sitemap Generator

`sitemap_gen` is a Python program, that crawls a web site and
outputs a XML sitemap.

It has been created by Vladimir Toncar and documented in
<http://toncar.cz/opensource/sitemap_gen.html>.

This version is a port of his fine program to Python 3.

## Update

These are my changes to the program, most of the work was done by Ehler,
This is forked from his repository here: https://git.b-ehlers.de/ehlers/sitemap_gen
All I have done so far is minor changes to how blocking works to expand it for
query strings. There might be a better approach but it works. 
File output is now segmented into files with 500 links each. Uses filename_# for pages  after the first


## Requirements

- Python 3.x
- reppy (<https://github.com/seomoz/reppy>),
  install with `pip3 install reppy`
- requests (<https://requests.readthedocs.io/>),
  will be installed when installing reppy.


## Usage

### Example

`python3 sitemap_gen.py -b doc -b bmp -o test_sitemap.xml http://www.your-site-name.com/index.html`

### Command Line Arguments

```text
python3 sitemap_gen.py <options> <starting URL>

Available options:
-h         --help                Print this text and exit

-b <ext>   --block <ext>         Exclude URLs with the matching text in them.
                                 Good for filtering out query strings like
                                 "?sort" to eliminate sorted urls. Alternatively
                                 add ? to disable all query strings

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
```

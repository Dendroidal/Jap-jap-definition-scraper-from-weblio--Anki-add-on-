# -*- coding: utf-8 -*-
#
# automatic definition generation from webli.jp

from bs4 import BeautifulSoup
import urllib.request
import urllib.parse
import urllib.error
import re

from anki.hooks import addHook
from .notetypes import isJapaneseNoteType

import threading

from aqt import mw
config = mw.addonManager.getConfig(__name__)

dicSrcFields = config['dicSrcFields']
defFields = config['defFields']

sub_def_cnt = 3  # number of subdefinitions displayed


# Builds and fetches the data for a word

######################################

class WordData:
    def __init__(self, word):
        self.word = word
        self.url = ("http://www.weblio.jp/content/"
                    + urllib.parse.quote(word.encode('utf-8')))

    def fetch_def(self):
        self.source = urllib.request.urlopen(self.url)
        self.soup = BeautifulSoup(self.source, features="html.parser")

        NetDicHeads = self.soup.find_all('div', {'class': "NetDicHead"})
        NetDicBodies = self.soup.find_all('div', {'class': "NetDicBody"})
        self.definitions = [WordDefinition(*pair, self.word)
                            for pair in list(zip(NetDicHeads, NetDicBodies))]


class WordDefinition:
    def __init__(self, head, body, word):
        self.head = head
        self.body = body
        self.word = word
        self.type = 'misc'
        if '［漢字］' in head.get_text():
            self.type = 'kanji'
        elif body.find('div', {'style': 'text-indent:0;'}):
            self.type = 'div_text-indent:0;'
        elif body.find('div', {'style': 'margin-left:1.2em;'}):
            self.type = 'div_margin-left:1.2em;'
        elif body.find('span', {'style': 'font-size:75%;'}) and \
                body.find('span', {'style': 'font-size:75%;'}).parent.find('div'):
            self.type = 'span_font-size:75%;'
        else:
            self.type = 'misc'

        self.find_yomikata()
        self.find_kanji()

        if head.b and '・' in head.b.get_text():
            end = head.b.get_text().split('・')[-1]
            self.stem = re.sub(end+'$', '', word)
        else:
            self.stem = word

        self.find_lines()

    def find_yomikata(self):
        if self.head.b and \
                not self.head.b.find('span', {'style': 'font-size:75%;'}):
            self.yomikata = re.sub(
                r'[・\s]', '', self.head.b.get_text())
        else:
            self.yomikata = ''

    def find_kanji(self):
        if '【' in self.head.get_text():
            self.kanji = re.sub('[▼▽（）《》]|・〈.*〉|〈|〉', '',
                                re.findall('【(.+)】', self.head.get_text())[0])
        elif self.head.find('span', {'style': 'font-size:75%;'}):
            self.head.find('span', {'style': 'font-size:75%;'}).extract()
            self.kanji = self.head.get_text().strip()
            #re.sub(r'<br/>$', '', self.head.get_text().strip())
        else:
            'no kanji'

    def find_lines(self):
        self.sublines = []
        if self.type == 'div_text-indent:0;':
            while self.body.find('div', {'style': 'text-indent:0;'}):
                new_line = self.body.find('div', {'style': 'text-indent:0;'})
                self.sublines.append(DefinitionLine(new_line, self.type))
                new_line.extract()
        elif self.type == 'div_margin-left:1.2em;':
            while self.body.find('div', {'style': 'margin-left:1.2em;'}):
                new_line = self.body.find('div', {'style': 'margin-left:1.2em;'}).parent
                self.sublines.append(DefinitionLine(new_line, self.type))
                new_line.extract()
        else:
            self.sublines.append(DefinitionLine(self.body, self.type))

    def display_def(self):
        return ('{}[{}]'.format(self.kanji, self.yomikata) +
                ''.join(l.display_line(self.stem)
                        for l in self.sublines[:sub_def_cnt]).strip()
                ).replace(' ', '')


class DefinitionLine:

    def __init__(self, soup, type='misc', depth=1):
        self.depth = depth
        self.sublines = []
        if type == 'div_text-indent:0;':
            while soup.find('div', {'style': 'text-indent:0;'}):
                new_line = soup.find('div', {'style': 'text-indent:0;'})
                self.sublines.append(DefinitionLine(new_line, type, depth+1))
                new_line.extract()
            raw_text_soup = soup.find('span', {'style': 'text-indent:0;'})
            raw_text_soup.extract()
            self.raw_text = raw_text_soup.get_text().strip()
            self.marker = soup.get_text().strip()
        elif type == 'div_margin-left:1.2em;':
            raw_text_soup = soup.find('div', {'style': 'margin-left:1.2em;'})
            raw_text_soup.extract()
            self.raw_text = raw_text_soup.get_text().strip()
            self.marker = soup.get_text().strip()
        elif type == 'span_font-size:75%;':
            self.marker = ""
            def_soup = soup.find('span', {'style': 'font-size:75%;'}).parent
            raw_text_soup = def_soup.find('div')
            self.raw_text = raw_text_soup.get_text().strip()
        else:
            self.marker = ""
            self.raw_text = soup.find('div').find('div').get_text()
        self.examples = re.findall(r'「[^「]*－[^「／]*」(?!に同じ)', self.raw_text)
        self.main_text = re.sub(r'「[^「]*－[^「]*」(?!に同じ)', '', self.raw_text)

        topic = re.findall(r'〘.*〙', self.main_text)
        self.topic = topic[0].replace('〘', '〔').replace('〙', '〕') if topic \
            else ''
        self.main_text = re.sub(r'〘.*〙', '', self.main_text)

        extra_info = re.findall(r'〔.*〕', self.main_text)
        self.main_text = re.sub(r'〔.*〕', '', self.main_text)

        synonym = re.findall(r'(?<=。)\s*→.*', self.main_text)
        self.main_text = re.sub(r'(?<=。)\s*→.*', '', self.main_text)

        antonym = re.findall(r'(?<=。)\s*⇔.*', self.main_text)
        self.antonym = antonym[0] if antonym else ''
        self.main_text = re.sub(r'(?<=。)\s*⇔.*', '', self.main_text)

        writing = re.findall(r'(?<=。)\s*《.*》', self.main_text)
        self.main_text = re.sub(r'(?<=。)\s*《.*》', '', self.main_text).strip()

    def display_line(self, stem):
        text = '　'*self.depth + self.marker + self.topic + '：　' + \
            self.main_text + \
            ''.join(re.sub(r'\s*－\s*・?', stem, e) for e in self.examples) + \
            self.antonym + '<br/>' + \
            ''.join(sub.display_line(stem) for sub in self.sublines[:sub_def_cnt])
        text = re.sub(r'[、，]', '、', text)
        return text


# Focus lost hook
##########################################################################


def onFocusLost(flag, n, fidx):
    src = None
    dst = None
    # japanese model?
    if not isJapaneseNoteType(n.model()['name']):
        return flag
    # have src and dst fields?
    fields = mw.col.models.fieldNames(n.model())
    src = fields[fidx]
    # Retro compatibility
    if src in dicSrcFields:
        srcIdx = dicSrcFields.index(src)
        dst = defFields[srcIdx]
    if not src or not dst:
        return flag
    # dst field exists?
    if dst not in n:
        return flag
    # dst field already filled?
    if n[dst]:
        return flag
    # grab source text
    srcTxt = mw.col.media.strip(n[src])
    if not srcTxt:
        return flag
    # update field
    #   #   word = urllib.parse.quote(n[src])
    words = n[src].split("、")

    dic = {}

    for word in words:
        dic[word] = {}
        dic[word]['data'] = WordData(word)
        dic[word]['thread'] = \
            threading.Thread(target=dic[word]['data'].fetch_def)
        dic[word]['thread'].start()

    for word in words:
        dic[word]['thread'].join()

    defns = sum((dic[word]['data'].definitions for word in words), [])
    # n[dst] = "<br/>".join("{}{}".format(word, fetchDef(word))
    #                      for word in words)
    n[dst] = "".join(defn.display_def() for defn in defns)
    return True


# Init
##########################################################################

addHook('editFocusLost', onFocusLost)

#!/usr/bin/python3
import gi
import ebooklib
from ebooklib import epub
import os.path
import re
from bs4 import BeautifulSoup

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from googletrans import Translator

class EBook(object):
    def __init__(self, filename):
        self.filename = filename
        self.__load_book()

    def __parse_epub_pages(self):
        page = 1
        self.pages = {}
        for item in self.book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            spans = [i for i in re.finditer(b'<span[^>]+/>', item.get_content())]
            for i in range(len(spans)):
                s = spans[i]
                n = spans[i+1].span() if i+1 < len(spans) else (-1, 0)
                start, end = s.span()
                s_text = s.string[start:end]
                if b'pagebreak' not in s_text:
                    continue
                title = re.findall(b'title=["\'](\d+)["\']', s_text)
                sid = re.findall(b'id=["\'](\d+)["\']', s_text)
                if len(sid) == 1:
                    page = int(sid[0])
                elif len(title) == 1:
                    page = int(title[0])
                else: # If there is no obvious page number, just increment
                    page += 1
                self.pages[page] = {
                    'ITEM_DOCUMENT': item,
                    'start': end,
                    'end': n[0]
                }

    def __load_book(self):
        ext = os.path.splitext(self.filename)[-1]
        if ext == '.epub':
            self.book = epub.read_epub(self.filename)
            self.__parse_epub_pages()
        elif ext == '.txt' or ext == '':
            self.book = open(self.filename, 'r').read()
        else:
            raise NotImplementedError('Unable to read file of type %s' % ext)

    def page(self, num):
        '''Read the specified page'''
        page_size = 256 # TODO: Break on word, not character
        if type(self.book) == str:
            book_len = len(self.book)
            loc = min(num*page_size, book_len)
            return self.book[loc:min(loc+page_size, book_len)]
        elif type(self.book) == epub.EpubBook:
            while True:
                if num not in self.pages.keys():
                    return ''
                page = self.pages[num]
                html = page['ITEM_DOCUMENT'].get_content()[page['start']:page['end']].decode()
                plain_text = BeautifulSoup(html).get_text('\n\t')
                if not plain_text.strip():
                    num += 1
                else:
                    break
            self.page_num = num
            return plain_text
        else:
            raise NotImplementedError('Unable to read page')

    def next_page(self):
        return self.page(self.page_num+1)

    def prev_page(self):
        return self.page(self.page_num-1)

    def current_page(self):
        return self.page_num

class TextViewWindow(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="EBook Word Translator")
        self.ebook = None

        self.set_default_size(700, 700)

        self.grid = Gtk.Grid()
        self.add(self.grid)

        self.create_textview()
        self.create_toolbar()

    def create_toolbar(self):
        toolbar = Gtk.Toolbar()
        self.grid.attach(toolbar, 0, 0, 3, 1)

        button_open = Gtk.ToolButton()
        button_open.set_icon_name("document-open-symbolic")
        toolbar.insert(button_open, 0)

        button_open.connect("clicked", self.on_button_open)

        toolbar.insert(Gtk.SeparatorToolItem(), 1)

        self.page_left = Gtk.ToolButton()
        self.page_left.set_icon_name("edit-redo-rtl-symbolic")
        toolbar.insert(self.page_left, 2)

        self.page_left.connect("clicked", self.prev_page)

        self.page_number = Gtk.Entry()
        self.page_number.set_editable(False)
        self.page_number.set_max_width_chars(4)
        self.page_number.set_width_chars(4)
        item = Gtk.ToolItem()
        item.add(self.page_number)
        toolbar.insert(item, 3)

        self.page_right = Gtk.ToolButton()
        self.page_right.set_icon_name("edit-undo-rtl-symbolic")
        toolbar.insert(self.page_right, 4)

        self.page_right.connect("clicked", self.next_page)

    def prev_page(self, arg):
        self.textbuffer.set_text(self.ebook.prev_page())
        self.set_page_visible()

    def next_page(self, arg):
        self.textbuffer.set_text(self.ebook.next_page())
        self.set_page_visible()

    def set_page_visible(self):
        self.page_number.set_text(str(self.ebook.current_page()))

    def on_button_open(self, arg):
        file_chooser = Gtk.FileChooserDialog(title='Choose an ebook', parent=self,
                                             action=Gtk.FileChooserAction.OPEN)
        file_chooser.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                                 Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        choice = file_chooser.run()
        if choice == Gtk.ResponseType.OK:
            file_path = file_chooser.get_filename()
            try:
                self.ebook = EBook(file_path)
                self.textbuffer.set_text(self.ebook.page(0))
                self.set_page_visible()
            except NotImplementedError as e:
                err = Gtk.MessageDialog(
                    transient_for=self,
                    flags=0,
                    message_type=Gtk.MessageType.WARNING,
                    buttons=Gtk.ButtonsType.OK_CANCEL,
                    text=str(e),
                )
                err.run()
                err.destroy()

        file_chooser.destroy()

    def create_textview(self):
        scrolledwindow = Gtk.ScrolledWindow()
        scrolledwindow.set_hexpand(True)
        scrolledwindow.set_vexpand(True)
        self.grid.attach(scrolledwindow, 0, 1, 3, 1)

        self.textview = Gtk.TextView()
        self.textbuffer = self.textview.get_buffer()
        self.textview.set_editable(False)
        self.textview.set_cursor_visible(False)
        self.textview.set_wrap_mode(Gtk.WrapMode.WORD)
        self.textview.connect("populate-popup", self.on_context_menu)
        scrolledwindow.add(self.textview)

    def on_context_menu(self, textview, menu):
        if type(menu) == Gtk.Menu:
            translate_item = Gtk.MenuItem(label="Translate")
            translate_item.connect("activate", self.translate_word)
            menu.insert(translate_item, 0)
            menu.show_all()

    def translate_word(self, translate_item):
        start, end = self.textbuffer.get_selection_bounds()
        text = self.textbuffer.get_slice(start, end, False)
        translator = Translator()
        translation = translator.translate(text, src='de')
        print(translation.text)

win = TextViewWindow()
win.connect("destroy", Gtk.main_quit)
win.show_all()
Gtk.main()

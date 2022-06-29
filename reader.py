#!/usr/bin/python3
import gi
import os
import re
from bs4 import BeautifulSoup

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
import translators as ts
from epr import epr

class EBook(object):
    def __init__(self, filename):
        self.filename = filename
        self.__load_book()


    def __load_book(self):
        ext = os.path.splitext(self.filename)[-1]
        if ext == '.epub':
            self.book = epr.Epub(self.filename)
            self.book.initialize()
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
        elif type(self.book) == epr.Epub:
            self.page_num = num
            page = self.book.contents[num]
            content = self.book.file.open(page).read().decode("utf-8")
            parser = epr.HTMLtoLines()
            try:
                parser.feed(content)
                parser.close()
            except:
                pass
            src_lines = parser.get_lines()
            return '\n'.join(src_lines)
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
        self.popup = None

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

        toolbar.insert(Gtk.SeparatorToolItem(), 5)

        settings = Gtk.FontButton()
        item = Gtk.ToolItem()
        item.add(settings)
        toolbar.insert(item, 6)

        settings.connect("font-set", self.text_settings)

    def text_settings(self, widget):
        font = widget.get_font_desc()
        self.textview.override_font(font)

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
        self.textview.set_justification(Gtk.Justification.FILL)
        self.textview.set_top_margin(20)
        self.textview.set_left_margin(20)
        self.textview.set_right_margin(20)
        self.textview.set_bottom_margin(20)
        self.textview.connect("populate-popup", self.on_context_menu)
        scrolledwindow.add(self.textview)

        self.textview.connect("button_release_event", self.translate_word_click)

    def on_context_menu(self, textview, menu):
        if type(menu) == Gtk.Menu:
            translate_item = Gtk.MenuItem(label="Translate")
            translate_item.connect("activate", self.translate_selection)
            menu.insert(translate_item, 0)
            menu.show_all()

    def popup_text(self, text):
        self.popup = Gtk.Menu()
        item = Gtk.MenuItem(label=text)
        self.popup.insert(item, 0)
        self.popup.show_all()
        self.popup.popup_at_pointer()

    def translate_word_click(self, textview, event_button):
        # Ignore translation if we're clicking away from an existing popup
        if self.popup != None:
            self.popup = None
            return
        # Ignore word translation if there is selected text (fallback to translate_selection())
        if self.textbuffer.get_has_selection():
            return
        if event_button.button == 1:
            pos_itr = self.textbuffer.get_iter_at_mark(self.textbuffer.get_insert())
            start_itr = pos_itr.copy()
            start_itr.backward_visible_word_start()
            end_itr = pos_itr.copy()
            end_itr.forward_visible_word_end()
            word = self.textbuffer.get_text(start_itr, end_itr, False)
            self.popup_text(ts.google(word, from_language='de'))

    def translate_selection(self, translate_item):
        start, end = self.textbuffer.get_selection_bounds()
        text = self.textbuffer.get_slice(start, end, False)
        self.popup_text(ts.google(text, from_language='de'))

win = TextViewWindow()
win.connect("destroy", Gtk.main_quit)
win.show_all()
Gtk.main()

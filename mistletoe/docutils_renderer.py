from itertools import chain
from os.path import splitext
from urllib.parse import urlparse, unquote

from docutils import nodes
from docutils.languages import get_language
from docutils.parsers.rst import directives, DirectiveError
from docutils.utils import new_document
from sphinx import addnodes

from mistletoe import Document
from mistletoe.base_renderer import BaseRenderer

# from mistletoe import block_token, span_token


class DocutilsRenderer(BaseRenderer):
    def __init__(self, extras=(), document=None, language="en", current_node=None):
        """
        Args:
            extras (list): allows subclasses to add even more custom tokens.
        """
        self.document = document
        if self.document is None:
            self.document = new_document("", settings=None)
        self.current_node = current_node or self.document
        self.language_module = language
        get_language(language)
        self._level_to_elem = {0: self.document}
        super().__init__(*chain((), extras))

    def render_children(self, token):
        for child in token.children:
            self.render(child)

    def render_document(self, token):
        # TODO deal with footnotes
        self.footnotes.update(token.footnotes)
        self.render_children(token)

    def render_paragraph(self, token):
        para = nodes.paragraph("")
        para.line = token.range[0]
        self.current_node.append(para)
        current_node = self.current_node
        self.current_node = para
        self.render_children(token)
        self.current_node = current_node

    def render_raw_text(self, token):
        self.current_node.append(nodes.Text(token.content, token.content))

    def render_escape_sequence(self, token):
        text = token.children[0].content
        self.current_node.append(nodes.Text(text, text))

    def render_line_break(self, token):
        self.current_node.append(nodes.raw("", "<br />", format="html"))

    def render_strong(self, token):
        node = nodes.strong()
        self.current_node.append(node)
        current_node = self.current_node
        self.current_node = node
        self.render_children(token)
        self.current_node = current_node

    def render_emphasis(self, token):
        node = nodes.emphasis()
        self.current_node.append(node)
        current_node = self.current_node
        self.current_node = node
        self.render_children(token)
        self.current_node = current_node

    def render_quote(self, token):
        quote = nodes.block_quote()
        quote.line = token.range[0]
        self.current_node.append(quote)
        current_node = self.current_node
        self.current_node = quote
        self.render_children(token)
        self.current_node = current_node

    def render_strikethrough(self, token):
        # TODO there is no existing node/role for this
        raise NotImplementedError

    def render_thematic_break(self, token):
        self.current_node.append(nodes.transition())

    def render_block_code(self, token):
        if token.language.startswith("{") and token.language.endswith("}"):
            return self.render_directive(token)
        text = token.children[0].content
        node = nodes.literal_block(text, text, language=token.language)
        self.current_node.append(node)

    def render_inline_code(self, token):
        text = token.children[0].content
        node = nodes.literal(text, text)
        self.current_node.append(node)

    def _is_section_level(self, level, section):
        return self._level_to_elem.get(level, None) == section

    def _add_section(self, section, level):
        parent_level = max(
            section_level
            for section_level in self._level_to_elem
            if level > section_level
        )
        parent = self._level_to_elem[parent_level]
        parent.append(section)
        self._level_to_elem[level] = section

        # Prune level to limit
        self._level_to_elem = dict(
            (section_level, section)
            for section_level, section in self._level_to_elem.items()
            if section_level <= level
        )

    def render_heading(self, token):
        # Test if we're replacing a section level first
        if isinstance(self.current_node, nodes.section):
            if self._is_section_level(token.level, self.current_node):
                self.current_node = self.current_node.parent

        title_node = nodes.title()
        title_node.line = token.range[0]

        new_section = nodes.section()
        new_section.line = token.range[0]
        new_section.append(title_node)

        self._add_section(new_section, token.level)

        self.current_node = title_node
        self.render_children(token)

        assert isinstance(self.current_node, nodes.title)
        text = self.current_node.astext()
        # if self.translate_section_name:
        #     text = self.translate_section_name(text)
        name = nodes.fully_normalize_name(text)
        section = self.current_node.parent
        section["names"].append(name)
        self.document.note_implicit_target(section, section)
        self.current_node = section

    def render_link(self, token):
        ref_node = nodes.reference()
        # Check destination is supported for cross-linking and remove extension
        destination = token.target
        _, ext = splitext(destination)
        # TODO check for other supported extensions, such as those specified in
        # the Sphinx conf.py file but how to access this information?
        # TODO this should probably only remove the extension for local paths,
        # i.e. not uri's starting with http or other external prefix.

        # if ext.replace('.', '') in self.supported:
        #     destination = destination.replace(ext, '')
        ref_node["refuri"] = destination
        # ref_node.line = self._get_line(token)
        if token.title:
            ref_node["title"] = token.title
        next_node = ref_node

        url_check = urlparse(destination)
        # If there's not a url scheme (e.g. 'https' for 'https:...' links),
        # or there is a scheme but it's not in the list of known_url_schemes,
        # then assume it's a cross-reference and pass it to Sphinx as an `:any:` ref.
        known_url_schemes = False  # self.config.get('known_url_schemes')
        if known_url_schemes:
            scheme_known = url_check.scheme in known_url_schemes
        else:
            scheme_known = bool(url_check.scheme)

        if not url_check.fragment and not scheme_known:
            wrap_node = addnodes.pending_xref(
                reftarget=unquote(destination),
                reftype="any",
                refdomain=None,  # Added to enable cross-linking
                refexplicit=True,
                refwarn=True,
            )
            # TODO also not correct sourcepos
            # wrap_node.line = self._get_line(token)
            if token.title:
                wrap_node["title"] = token.title
            wrap_node.append(ref_node)
            next_node = wrap_node

        self.current_node.append(next_node)
        current_node = self.current_node
        self.current_node = ref_node
        self.render_children(token)
        self.current_node = current_node

    def render_image(self, token):
        img_node = nodes.image()
        img_node["uri"] = token.src

        # TODO how should image alt children be stored?
        img_node["alt"] = ""
        # if token.children and isinstance(token.children[0], block_token.RawText):
        #     img_node["alt"] = token.children[0].content
        #     token.children[0].content = ""

        self.current_node.append(img_node)
        current_node = self.current_node
        self.current_node = img_node
        self.render_children(token)
        self.current_node = current_node

    def render_list(self, token):
        list_node = None
        if token.start is not None:
            list_node = nodes.enumerated_list()
            # TODO deal with token.start?
            # TODO support numerals/letters for lists
            # (see https://stackoverflow.com/a/48372856/5033292)
            # See docutils/docutils/parsers/rst/states.py:Body.enumerator
            # list_node['enumtype'] = 'arabic', 'loweralpha', 'upperroman', etc.
            # list_node['start']
            # list_node['prefix']
            # list_node['suffix']
        else:
            list_node = nodes.bullet_list()
        # TODO deal with token.loose?
        # TODO list range
        # list_node.line = token.range[0]

        self.current_node.append(list_node)
        current_node = self.current_node
        self.current_node = list_node
        self.render_children(token)
        self.current_node = current_node

    def render_list_item(self, token):
        item_node = nodes.list_item()
        # TODO list item range
        # node.line = token.range[0]
        self.current_node.append(item_node)
        current_node = self.current_node
        self.current_node = item_node
        self.render_children(token)
        self.current_node = current_node

    def render_table(self, token):
        raise NotImplementedError

    def render_table_row(self, token):
        raise NotImplementedError

    def render_table_cell(self, token):
        raise NotImplementedError

    def render_auto_link(self, token):
        raise NotImplementedError

    def render_directive(self, token):
        name = token.language[1:-1]
        # TODO directive name white/black lists
        content = token.children[0].content
        directive_class, messages = directives.directive(
            name, self.language_module, self.document
        )
        if not directive_class:
            # TODO deal with unknown directive
            self.current_node += messages
            return

        directive_instance = directive_class(
            name=name,
            # the list of positional arguments
            arguments=[],
            # a dictionary mapping option names to values
            options={},
            # the directive content line by line
            content=content.splitlines(),
            # the absolute line number of the first line of the directive
            lineno=token.range[0],
            # the line offset of the first line of the content
            content_offset=0,
            # a string containing the entire directive
            block_text=content,
            state=MockState(self, token.range[0]),
            state_machine=MockStateMachine(self, token.range[0]),
        )

        try:
            result = directive_instance.run()
        except DirectiveError as error:
            msg_node = self.document.reporter.system_message(
                error.level, error.msg, line=token.range[0]
            )
            msg_node += nodes.literal_block(content, content)
            result = [msg_node]
        except AttributeError:
            # TODO deal with directives that call unimplemented methods of State/Machine
            raise
        assert isinstance(
            result, list
        ), f'Directive "{name}" must return a list of nodes.'
        for i in range(len(result)):
            assert isinstance(
                result[i], nodes.Node
            ), f'Directive "{name}" returned non-Node object (index {i}): {result[i]}'
        self.current_node += result


class MockState:
    def __init__(self, renderer, lineno):
        self._renderer = renderer
        self._lineno = lineno
        self.document = renderer.document

    def nested_parse(self, content, content_offset, root_node):
        nested_renderer = DocutilsRenderer(
            document=self.document,
            language=self._renderer.language_module,
            current_node=root_node,
        )
        # TODO deal with starting line number
        nested_renderer.render(Document(content))

    # def inline_text(self, text, lineno):
    #     return textnodes, messages


class MockStateMachine:
    def __init__(self, renderer, lineno):
        self._renderer = renderer
        self._lineno = lineno
        self.document = renderer.document
        self.reporter = self.document.reporter

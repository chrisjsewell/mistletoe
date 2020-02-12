from itertools import chain
from os.path import splitext
import re
from urllib.parse import urlparse, unquote

from docutils import frontend, nodes, parsers
from docutils.frontend import OptionParser
from docutils.languages import get_language
from docutils.parsers.rst import directives, DirectiveError, roles
from docutils.parsers.rst import Parser as RSTParser
from docutils.utils import new_document
from sphinx import addnodes
import yaml

from mistletoe import Document
from mistletoe.base_renderer import BaseRenderer
from mistletoe.latex_token import Math

from mistletoe import span_token


class MystParser(parsers.Parser):
    """Docutils parser for CommonMark + Math + Tables + RST Extensions """

    supported = ("md", "markdown")
    translate_section_name = None

    default_config = {"known_url_schemes": None}

    settings_spec = (
        "Myst Parser Options",
        None,
        (
            (
                'Recognize and link to standalone PEP references (like "PEP 258").',
                ["--pep-references"],
                {"action": "store_true", "validator": frontend.validate_boolean},
            ),
            (
                "Base URL for PEP references "
                '(default "http://www.python.org/dev/peps/").',
                ["--pep-base-url"],
                {
                    "metavar": "<URL>",
                    "default": "http://www.python.org/dev/peps/",
                    "validator": frontend.validate_url_trailing_slash,
                },
            ),
            (
                'Template for PEP file part of URL. (default "pep-%04d")',
                ["--pep-file-url-template"],
                {"metavar": "<URL>", "default": "pep-%04d"},
            ),
            (
                'Recognize and link to standalone RFC references (like "RFC 822").',
                ["--rfc-references"],
                {"action": "store_true", "validator": frontend.validate_boolean},
            ),
            (
                'Base URL for RFC references (default "http://tools.ietf.org/html/").',
                ["--rfc-base-url"],
                {
                    "metavar": "<URL>",
                    "default": "http://tools.ietf.org/html/",
                    "validator": frontend.validate_url_trailing_slash,
                },
            ),
            (
                "Set number of spaces for tab expansion (default 8).",
                ["--tab-width"],
                {
                    "metavar": "<width>",
                    "type": "int",
                    "default": 8,
                    "validator": frontend.validate_nonnegative_int,
                },
            ),
            (
                "Remove spaces before footnote references.",
                ["--trim-footnote-reference-space"],
                {"action": "store_true", "validator": frontend.validate_boolean},
            ),
            (
                "Leave spaces before footnote references.",
                ["--leave-footnote-reference-space"],
                {"action": "store_false", "dest": "trim_footnote_reference_space"},
            ),
            (
                "Disable directives that insert the contents of external file "
                '("include" & "raw"); replaced with a "warning" system message.',
                ["--no-file-insertion"],
                {
                    "action": "store_false",
                    "default": 1,
                    "dest": "file_insertion_enabled",
                    "validator": frontend.validate_boolean,
                },
            ),
            (
                "Enable directives that insert the contents of external file "
                '("include" & "raw").  Enabled by default.',
                ["--file-insertion-enabled"],
                {"action": "store_true"},
            ),
            (
                'Disable the "raw" directives; replaced with a "warning" '
                "system message.",
                ["--no-raw"],
                {
                    "action": "store_false",
                    "default": 1,
                    "dest": "raw_enabled",
                    "validator": frontend.validate_boolean,
                },
            ),
            (
                'Enable the "raw" directive.  Enabled by default.',
                ["--raw-enabled"],
                {"action": "store_true"},
            ),
            (
                "Token name set for parsing code with Pygments: one of "
                '"long", "short", or "none (no parsing)". Default is "long".',
                ["--syntax-highlight"],
                {
                    "choices": ["long", "short", "none"],
                    "default": "long",
                    "metavar": "<format>",
                },
            ),
            (
                "Change straight quotation marks to typographic form: "
                'one of "yes", "no", "alt[ernative]" (default "no").',
                ["--smart-quotes"],
                {
                    "default": False,
                    "metavar": "<yes/no/alt>",
                    "validator": frontend.validate_ternary,
                },
            ),
            (
                'Characters to use as "smart quotes" for <language>. ',
                ["--smartquotes-locales"],
                {
                    "metavar": "<language:quotes[,language:quotes,...]>",
                    "action": "append",
                    "validator": frontend.validate_smartquotes_locales,
                },
            ),
            (
                "Inline markup recognized at word boundaries only "
                "(adjacent to punctuation or whitespace). "
                "Force character-level inline markup recognition with "
                '"\\ " (backslash + space). Default.',
                ["--word-level-inline-markup"],
                {"action": "store_false", "dest": "character_level_inline_markup"},
            ),
            (
                "Inline markup recognized anywhere, regardless of surrounding "
                "characters. Backslash-escapes must be used to avoid unwanted "
                "markup recognition. Useful for East Asian languages. "
                "Experimental.",
                ["--character-level-inline-markup"],
                {
                    "action": "store_true",
                    "default": False,
                    "dest": "character_level_inline_markup",
                },
            ),
        ),
    )

    config_section = "myst parser"
    config_section_dependencies = ("parsers",)

    def parse(self, inputstring, document):
        # TODO add conf.py configurable settings
        self.config = self.default_config.copy()
        try:
            new_cfg = self.document.settings.env.config.myst_config
            self.config.update(new_cfg)
        except AttributeError:
            pass
        renderer = DocutilsRenderer(document=document)
        with renderer:
            renderer.render(Document(inputstring))


# TODO add FieldList block token, see:
# https://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html#field-lists
# TODO block comments (preferably not just HTML)


class Role(span_token.SpanToken):
    """
    Inline role tokens. ("{name}`some code`")
    """

    pattern = re.compile(
        r"(?<!\\|`)(?:\\\\)*{([-_0-9a-zA-A]*)}(`+)(?!`)(.+?)(?<!`)\2(?!`)", re.DOTALL
    )
    parse_inner = False
    precedence = 6  # higher precedence than InlineCode

    def __init__(self, match):
        self.name = match.group(1)
        content = match.group(3)
        self.children = (
            span_token.RawText(" ".join(re.split("[ \n]+", content.strip()))),
        )


class DocutilsRenderer(BaseRenderer):
    def __init__(self, extras=(), document=None, current_node=None, config=None):
        """
        Args:
            extras (list): allows subclasses to add even more custom tokens.
        """
        self.document = document
        self.config = config or {}
        if self.document is None:
            settings = OptionParser(components=(RSTParser,)).get_default_values()
            self.document = new_document("", settings=settings)
        self.current_node = current_node or self.document
        self.language_module = self.document.settings.language_code
        get_language(self.language_module)
        self._level_to_elem = {0: self.document}
        super().__init__(*chain((Math, Role), extras))

    def mock_sphinx_env(self):
        """Load sphinx roles, directives, etc."""
        from sphinx.application import builtin_extensions, Sphinx
        from sphinx.config import Config
        from sphinx.environment import BuildEnvironment
        from sphinx.events import EventManager
        from sphinx.project import Project
        from sphinx.registry import SphinxComponentRegistry

        class MockSphinx(Sphinx):
            def __init__(self):
                self.registry = SphinxComponentRegistry()
                self.config = Config({}, {})
                self.events = EventManager(self)
                self.html_themes = {}
                self.extensions = {}
                for extension in builtin_extensions:
                    self.registry.load_extension(self, extension)
                # fresh env
                self.doctreedir = ""
                self.srcdir = ""
                self.project = Project(srcdir="", source_suffix=".md")
                self.project.docnames = ["mock_docname"]
                self.env = BuildEnvironment()
                self.env.setup(self)
                self.env.temp_data["docname"] = "mock_docname"

        app = MockSphinx()
        self.document.settings.env = app.env
        return app

    def render_children(self, token):
        for child in token.children:
            self.render(child)

    def render_document(self, token):
        # TODO deal with footnotes
        self.footnotes.update(token.footnotes)
        self.render_children(token)
        return self.document

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

    def render_math(self, token):
        if token.content.startswith("$$"):
            content = token.content[2:-2]
            node = nodes.math_block(content, content, nowrap=False, number=None)
        else:
            content = token.content[1:-1]
            node = nodes.math(content, content)
        self.current_node.append(node)

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
        # TODO escape urls?
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
        known_url_schemes = self.config.get("known_url_schemes", None)
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
        # TODO render_table
        raise NotImplementedError

    def render_table_row(self, token):
        raise NotImplementedError

    def render_table_cell(self, token):
        raise NotImplementedError

    def render_auto_link(self, token):
        # TODO render_auto_link
        raise NotImplementedError

    def render_role(self, token):
        content = token.children[0].content
        name = token.name
        # TODO role name white/black lists
        lineno = 0  # TODO get line number
        inliner = MockInliner(self)
        role_func, messages = roles.role(
            name, self.language_module, lineno, self.document.reporter
        )
        rawsource = ":{}:`{}`".format(name, content)
        # # backslash escapes converted to nulls (``\x00``)
        text = span_token.EscapeSequence.strip(content)
        if role_func:
            nodes, messages2 = role_func(name, rawsource, text, lineno, inliner)
            # return nodes, messages + messages2
            self.current_node += nodes
        else:
            message = self.document.reporter.error(
                'Unknown interpreted text role "{}".'.format(name), line=lineno
            )
            # return ([self.problematic(content, content, msg)], messages + [msg])
            problematic = inliner.problematic(text, rawsource, message)
            self.current_node += problematic

    def render_directive(self, token):
        name = token.language[1:-1]
        content = token.children[0].content
        options = {}
        if content.startswith("---"):
            content = "\n".join(content.splitlines()[1:])
            # get YAML options
            match = re.search(r"^-{3,}", content, re.MULTILINE)
            if match:
                yaml_block = content[: match.start()]
                content = content[match.end() :]  # TODO advance line number
            else:
                yaml_block = content
                content = ""
            try:
                options = yaml.safe_load(yaml_block) or {}
            except yaml.parser.ParserError:
                # TODO handle/report yaml parse error
                pass
            # TODO check options are an un-nested dict?

        # TODO directive name white/black lists
        directive_class, messages = directives.directive(
            name, self.language_module, self.document
        )
        if not directive_class:
            # TODO deal with unknown directive
            self.current_node += messages
            return

        try:
            arguments = self.parse_directive_arguments(directive_class, token.arguments)
        except RuntimeError:
            # TODO handle/report error
            raise

        state_machine = MockStateMachine(self, token.range[0])

        directive_instance = directive_class(
            name=name,
            # the list of positional arguments
            arguments=arguments,
            # a dictionary mapping option names to values
            # TODO option parsing
            options=options,
            # the directive content line by line
            content=content.splitlines(),
            # the absolute line number of the first line of the directive
            lineno=token.range[0],
            # the line offset of the first line of the content
            content_offset=0,
            # a string containing the entire directive
            block_text=content,
            state=MockState(self, state_machine, token.range[0]),
            state_machine=state_machine,
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
        ), 'Directive "{}" must return a list of nodes.'.format(name)
        for i in range(len(result)):
            assert isinstance(
                result[i], nodes.Node
            ), 'Directive "{}" returned non-Node object (index {}): {}'.format(
                name, i, result[i]
            )
        self.current_node += result

    @staticmethod
    def parse_directive_arguments(directive, arg_text):
        required = directive.required_arguments
        optional = directive.optional_arguments
        arguments = arg_text.split()
        if len(arguments) < required:
            raise RuntimeError(
                "{} argument(s) required, {} supplied".format(required, len(arguments))
            )
        elif len(arguments) > required + optional:
            if directive.final_argument_whitespace:
                arguments = arg_text.split(None, required + optional - 1)
            else:
                raise RuntimeError(
                    "maximum {} argument(s) allowed, {} supplied".format(
                        required + optional, len(arguments)
                    )
                )
        return arguments


class MockInliner:
    def __init__(self, renderer):
        self._renderer = renderer
        self.document = renderer.document
        self.reporter = renderer.document.reporter
        self.parent = renderer.current_node
        self.language = renderer.language_module

    def problematic(self, text, rawsource, message):
        msgid = self.document.set_id(message, self.parent)
        problematic = nodes.problematic(rawsource, rawsource, refid=msgid)
        prbid = self.document.set_id(problematic)
        message.add_backref(prbid)
        return problematic

    # TODO add parse method


class MockState:
    def __init__(self, renderer, state_machine, lineno):
        self._renderer = renderer
        self._lineno = lineno
        self.document = renderer.document
        self.state_machine = state_machine

    def nested_parse(
        self,
        block,
        input_offset,
        node,
        match_titles=False,
        state_machine_class=None,
        state_machine_kwargs=None,
    ):
        current_match_titles = self.state_machine.match_titles
        self.state_machine.match_titles = match_titles
        nested_renderer = DocutilsRenderer(document=self.document, current_node=node)
        self.state_machine.match_titles = current_match_titles
        # TODO deal with starting line number
        nested_renderer.render(Document(block))

    def inline_text(self, text, lineno):
        # TODO return messages?
        messages = []
        paragraph = nodes.paragraph("")
        renderer = DocutilsRenderer(document=self.document, current_node=paragraph)
        renderer.render(Document(text))
        textnodes = []
        if paragraph.children:
            # first child should be paragraph
            textnodes = paragraph.children[0].children
        return textnodes, messages

    def block_quote(self, indented, line_offset):
        # TODO block_quote
        elements = []
        return elements


class MockStateMachine:
    def __init__(self, renderer, lineno):
        self._renderer = renderer
        self._lineno = lineno
        self.document = renderer.document
        self.reporter = self.document.reporter
        self.node = renderer.current_node
        self.match_titles = True

    def get_source_and_line(self, lineno=None):
        """Return (source, line) tuple for current or given line number."""
        # TODO return correct line source
        return "", lineno or self._lineno

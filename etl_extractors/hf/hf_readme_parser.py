import mistune
from html_to_markdown import convert as convert_to_md
import logging
from datetime import datetime
import graphviz
import textwrap
import uuid


class MDParserChunker:

    def __init__(self):

        self.logger = None # TODO: Add logger support

    def generate_ast(self, model_card):
        """
        Parses model card and restructures the abstract syntax tree (AST) from `mistune`
        into a hierarchical tree based on heading levels (H1, H2, etc.).

        The output format for each node is a dictionary with keys:
        - "section_type": The type of the markdown element (e.g., 'Heading', 'Paragraph').
        - "content": The direct text content of the element. For containers, this is empty.
        - "children": A list of child nodes, forming the hierarchy.

        Args:
            model_card: A string containing the model_card text.

        Returns:
            A list of dictionaries representing the hierarchical structure of the document.
        """

        def build_hierarchical_tree(flat_nodes):
            hierarchical_tree = []
            parent_stack = [{"children": hierarchical_tree, "level": 0}]

            for node in flat_nodes:
                if node.get("section_type") == "heading":
                    heading_level = node.get("level", 1)
                    while parent_stack[-1].get("level", 0) >= heading_level:
                        parent_stack.pop()
                    parent_stack[-1]["children"].append(node)
                    parent_stack.append(node)
                else:
                    parent_stack[-1]["children"].append(node)
            return hierarchical_tree

        def _get_content(node):
            content = []
            children_list = node.get("children")
            if children_list:
                for child in children_list:
                    content.append(_get_content(child))
            return node.get("raw", "".join(content))

        def _flatten_and_transform(node):
            node_type = node.get("type", "undefined_type")

            if node_type in [
                "blank_line",
                "thematic_break",
                "softbreak",
                "linebreak",
                "image",
            ]:
                return []

            if node_type == "block_html":
                html_str = node.get("raw", "")
                if not html_str.strip():
                    return []

                md_str = convert_to_md(html_str)
                sub_ast = mistune_generator(md_str)

                unwrapped_nodes = []
                for sub_node in sub_ast:
                    unwrapped_nodes.extend(_flatten_and_transform(sub_node))
                return unwrapped_nodes

            transformed = {"section_type": node_type, "content": "", "children": []}

            if node_type in ["text", "codespan", "block_code", "inline_html"]:
                transformed["content"] = node.get("raw", "")

            elif node_type == "link":
                transformed["content"] = node.get("attrs", {}).get("url", "NA")

            elif node_type == "heading":
                transformed["content"] = _get_content(node)
                transformed["level"] = node.get("attrs", {}).get("level", 1)
                transformed["children"] = []
                return [transformed]

            if node.get("children"):
                for child in node.get("children"):
                    child_transformed_list = _flatten_and_transform(child)
                    transformed["children"].extend(child_transformed_list)

            return [transformed]

        mistune_generator = mistune.create_markdown(
            renderer="ast", escape=False, plugins=["table"]
        )
        doc = mistune_generator(model_card)

        flat_nodes = []
        for node in doc:
            flat_nodes.extend(_flatten_and_transform(node))

        return build_hierarchical_tree(flat_nodes)

    def generate_graphviz(self, ast, output_filename):

        def add_nodes_edges(graph, nodes, parent_name=None):
            for i, node in enumerate(nodes):
                node_name = f"{parent_name}_{i}" if parent_name else f"root_{i}"

                section_type = node.get("section_type", "Unknown")
                content = node.get("content", "")

                label = section_type
                if content:
                    wrapped_content = textwrap.fill(str(content), width=50)
                    label += f'\n\n"{wrapped_content}"'

                graph.node(node_name, label=label)

                if parent_name:
                    graph.edge(parent_name, node_name)

                if node.get("children"):
                    add_nodes_edges(graph, node["children"], parent_name=node_name)

        dot = graphviz.Digraph("AST", comment="Abstract Syntax Tree")
        dot.attr("node", shape="box", style="rounded")
        dot.attr(rankdir="TB")

        add_nodes_edges(dot, ast)

        dot.render(output_filename, view=True, format="svg", cleanup=True)

    def generate_chunks(self, ast, min_len=20):
        """
        the chunking process main loop

        Args:
            ast (list): The list of nodes representing the document's AST.

        Returns:
            list: A list of dictionaries, where each dictionary represents a chunk.
        """

        def _word_count(sen):
            return len(sen.split())

        def _get_all_text(node):
            """
            recursively traverses a node and its children to extract all text content, returning it as a single string
            """

            # base case: if the node is a text node, return its content.
            if node.get("section_type") in ["text"]:
                return node.get("content", "")

            all_text = ""
            # include the node's own content if it exists
            if node.get("content", "") and node.get("section_type") not in [
                "link"
            ]:  # if there is content in node but not link node
                all_text += node.get("content", "") + " "

            # recursive step: if the node has children, process them
            if "children" in node and node["children"]:
                for child in node["children"]:
                    all_text += _get_all_text(child) + " "

            return all_text.strip()

        def _process_heading_node(
            heading_node,
            parent_id,
            parent_heading_text=None,
        ):
            """
            recursively processes a heading node and its children to create a hierarchy of chunks.

            1. creates a 'section' chunk for the heading itself.
            2. creates 'granular' or 'code' chunks for its direct children.
            3. finds child headings and calls itself on them to build the tree.
            """

            if heading_node.get("section_type") not in SECTION_TYPES:
                return

            section_id = str(uuid.uuid4())
            section_text = _get_all_text(heading_node)
            heading_text = heading_node["content"]

            if section_text.strip():
                all_chunks.append(
                    {
                        "id": section_id,
                        "type": "section",
                        "length": len(section_text.strip().split()),
                        "parent": parent_id,
                        "htext": heading_text,
                        "phtext": parent_heading_text,
                        "text": section_text.strip(),
                    }
                )

            if not heading_node.get("children"):
                return

            short_node_buffer = ""

            for child_node in heading_node["children"]:
                # if a child is another heading, recurse.
                if child_node.get("section_type") in SECTION_TYPES:

                    # the current section becomes the parent for the next call.
                    _process_heading_node(
                        child_node,
                        section_id,
                        heading_text,
                    )

                # if a child is a granular type, create a granular chunk
                else:

                    if child_node.get("section_type") in CODE_TYPES:
                        granular_text = _get_all_text(child_node)
                        granular_type = "code"

                    elif child_node.get("section_type") in TABLE_TYPES:
                        # implement table chunking logic
                        granular_text = "TABLE (TO BE IMPLEMENTED)"
                        granular_type = "table"

                    else:
                        granular_text = _get_all_text(child_node)
                        granular_type = "granular"

                    if not granular_text:
                        continue

                    if granular_type in ["code", "table"]:
                        all_chunks.append(
                            {
                                "id": str(uuid.uuid4()),
                                "type": granular_type,
                                "length": len(granular_text.split()),
                                "parent": section_id,
                                "phtext": heading_text,
                                "text": granular_text,
                            }
                        )
                        continue

                    length = len(granular_text.split())

                    if length <= min_len:
                        short_node_buffer += " " + granular_text
                        continue

                    if short_node_buffer:
                        granular_text = short_node_buffer + granular_text
                        short_node_buffer = ""

                    all_chunks.append(
                        {
                            "id": str(uuid.uuid4()),
                            "type": granular_type,
                            "length": len(granular_text.split()),
                            "parent": section_id,
                            "phtext": heading_text,
                            "text": granular_text.strip(),
                        }
                    )

            if short_node_buffer.strip():
                all_chunks.append(
                    {
                        "id": str(uuid.uuid4()),
                        "type": "granular",
                        "length": len(short_node_buffer.split()),
                        "parent": section_id,
                        "phtext": heading_text,
                        "text": short_node_buffer.strip(),
                    }
                )

        SECTION_TYPES = ["heading"]
        TABLE_TYPES = ["table"]
        CODE_TYPES = ["codespan", "block_code"]
        CONTAINER_TYPES = ["paragraph", "list"]

        all_chunks = []
        orphan_list = []

        # --- main loop ---
        for top_level_node in ast:
            node_type = top_level_node.get("section_type", "")

            # --- the node is a section container  ---
            if node_type in SECTION_TYPES:
                _process_heading_node(top_level_node, None)

            # --- the node is a top level granular orphan ---
            else:
                orphan_list.append(top_level_node)

        if orphan_list:
            orphan_text = ""
            for orphan in orphan_list:
                orphan_text += " " + _get_all_text(orphan)

            all_chunks.append(
                {
                    "type": "orphan",
                    "length": len(orphan_text.split()),
                    "id": str(uuid.uuid4()),
                    "parent": None,
                    "phtext": None,
                    "text": orphan_text.strip(),
                }
            )

        return all_chunks
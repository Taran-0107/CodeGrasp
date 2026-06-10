from tree_sitter import Parser, Node, Language
from app.utils.logger import logger

class ParserService:
    @staticmethod
    def extract_entities(source_code_bytes: bytes, file_path: str, language_name: str = "python") -> list[dict]:
        """
        Parses source code using Tree-sitter and extracts entities: classes, functions, and imports.
        It also identifies dependency links (base classes, function calls).
        """
        try:
            if language_name == "python":
                import tree_sitter_python
                language = Language(tree_sitter_python.language())
            else:
                logger.error(f"Language '{language_name}' is not supported yet.")
                return []
            
            parser = Parser(language)
        except Exception as e:
            logger.error(f"Failed to load tree-sitter language '{language_name}': {e}")
            return []

        try:
            tree = parser.parse(source_code_bytes)
        except Exception as e:
            logger.error(f"Failed to parse AST for {file_path}: {e}")
            return []

        entities = []

        def traverse(node: Node, parent_scope: list[str]):
            current_scope = list(parent_scope)
            is_entity = False
            entity_type = None
            entity_name = None

            if node.type == "class_definition":
                is_entity = True
                entity_type = "class"
                name_node = node.child_by_field_name("name")
                if name_node:
                    entity_name = name_node.text.decode("utf-8", errors="ignore")
                    current_scope.append(entity_name)
            elif node.type == "function_definition":
                is_entity = True
                entity_type = "function"
                name_node = node.child_by_field_name("name")
                if name_node:
                    entity_name = name_node.text.decode("utf-8", errors="ignore")
                    current_scope.append(entity_name)
            
            # Extract import entities
            elif node.type == "import_statement":
                # import a, b.c, d as e
                modules = []
                for child in node.children:
                    if child.type == "dotted_name":
                        modules.append(child.text.decode("utf-8", errors="ignore"))
                    elif child.type == "aliased_import":
                        name_child = child.child_by_field_name("name")
                        if name_child:
                            modules.append(name_child.text.decode("utf-8", errors="ignore"))
                for mod in modules:
                    entities.append({
                        "entity_type": "import",
                        "entity_name": mod,
                        "start_line": node.start_point[0] + 1,
                        "end_line": node.end_point[0] + 1,
                        "code_snippet": source_code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore"),
                        "dependencies": []
                    })
            elif node.type == "import_from_statement":
                # from a.b import x, y as z
                module_name = ""
                module_node = node.child_by_field_name("module_name")
                if module_node:
                    module_name = module_node.text.decode("utf-8", errors="ignore")

                imported = []
                for child in node.children:
                    if child.type == "dotted_name":
                        imported.append(child.text.decode("utf-8", errors="ignore"))
                    elif child.type == "aliased_import":
                        name_child = child.child_by_field_name("name")
                        if name_child:
                            imported.append(name_child.text.decode("utf-8", errors="ignore"))
                    elif child.type == "wildcard_import":
                        imported.append("*")

                # Fallback to general identifier children inside from-import if dotted_name wasn't matched directly
                if not imported:
                    for child in node.children:
                        if child != module_node and child.type == "identifier":
                            imported.append(child.text.decode("utf-8", errors="ignore"))

                for imp in imported:
                    full_name = f"{module_name}.{imp}" if module_name else imp
                    entities.append({
                        "entity_type": "import",
                        "entity_name": full_name,
                        "start_line": node.start_point[0] + 1,
                        "end_line": node.end_point[0] + 1,
                        "code_snippet": source_code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore"),
                        "dependencies": []
                    })

            if is_entity and entity_name:
                code_snippet = source_code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")
                dependencies = []

                # Find base class dependencies
                if entity_type == "class":
                    # Superclasses are in the argument_list node of the class_definition
                    arg_list = node.child_by_field_name("superclasses")
                    if not arg_list:
                        # Fallback traversal to locate argument_list
                        for child in node.children:
                            if child.type == "argument_list":
                                arg_list = child
                                break
                    if arg_list:
                        for child in arg_list.children:
                            if child.type in ("identifier", "attribute"):
                                dependencies.append(child.text.decode("utf-8", errors="ignore"))

                # Traverse body to find function calls (dependencies)
                def find_calls(sub_node: Node):
                    # Stop traversal at nested definitions (they'll be parsed as their own entities)
                    if sub_node != node and sub_node.type in ("class_definition", "function_definition"):
                        return

                    if sub_node.type == "call":
                        func_node = sub_node.child_by_field_name("function")
                        if func_node:
                            call_name = func_node.text.decode("utf-8", errors="ignore")
                            dependencies.append(call_name)

                    for child in sub_node.children:
                        find_calls(child)

                body_node = node.child_by_field_name("body")
                if body_node:
                    find_calls(body_node)
                else:
                    find_calls(node)

                entities.append({
                    "entity_type": entity_type,
                    "entity_name": ".".join(current_scope),
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "code_snippet": code_snippet,
                    "dependencies": list(set(dependencies))
                })

            # Traverse child nodes
            for child in node.children:
                traverse(child, current_scope)

        traverse(tree.root_node, [])
        return entities

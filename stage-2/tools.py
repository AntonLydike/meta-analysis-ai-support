import os
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import pypdfium2 as pdfium


@dataclass(frozen=True)
class Document:
    id: int  # integer id
    zid: str  # permanent zotero ID
    title: str  # article title
    authors: tuple[str]  # list of full author names
    attachments: tuple[str]  # paths to attachment files

    def get_text(self) -> str:
        def readall(f: str):
            if f.endswith(".pdf"):
                # parse pdf:
                return "\n".join(
                    str(page.get_textpage().get_text_bounded())
                    for page in pdfium.PdfDocument(f)
                )
            else:
                with open(f, "r") as file:
                    return file.read()

        return (
            "\n\n---".join(map(readall, self.attachments))
            if self.attachments
            else "no files found"
        )


def load_rdf(file_path: str) -> list[Document]:
    # Support both raw XML strings and direct file paths
    tree = ET.parse(file_path)
    root = tree.getroot()
    base_path = os.path.dirname(file_path)

    # 1. Define XML namespaces used by Zotero RDF exports
    ns = {
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "bib": "http://purl.org/net/biblio#",
        "dc": "http://purl.org/dc/elements/1.1/",
        "z": "http://www.zotero.org/namespaces/export#",
        "foaf": "http://xmlns.com/foaf/0.1/",
        "link": "http://purl.org/rss/1.0/modules/link/",
    }

    # 2. Map attachment IDs to their respective file paths
    # <z:Attachment rdf:about="#item_32437"> -> <z:path rdf:resource="files/...pdf"/>
    attachment_map = {}
    for attachment in root.findall(".//z:Attachment", ns):
        about_attr = attachment.get(f"{{{ns['rdf']}}}about", "")
        # Strip out the '#' prefix to cleanly match ID tracking tokens
        attach_id = about_attr.lstrip("#")

        path_node = attachment.find("z:path", ns)
        if path_node is not None:
            path_resource = path_node.get(f"{{{ns['rdf']}}}resource", "")
            if attach_id and path_resource:
                attachment_map[attach_id] = os.path.join(
                    base_path, unicodedata.normalize("NFD", path_resource)
                )

    # 3. Process primary Article records and link their attachments
    documents = []
    for article in root.findall(".//bib:Article", ns):
        # Extract unique ID
        about_attr = article.get(f"{{{ns['rdf']}}}about", "")
        doc_id = about_attr.lstrip("#")

        # Extract Title
        title_node = article.find("dc:title", ns)
        title = (
            title_node.text.strip()
            if title_node is not None and title_node.text
            else "Untitled"
        )

        # Extract Authors (combine Given Names and Surnames)
        authors = []
        for person in article.findall(".//foaf:Person", ns):
            given = person.find("foaf:givenName", ns)
            surname = person.find("foaf:surname", ns)

            given_text = given.text.strip() if given is not None and given.text else ""
            surname_text = (
                surname.text.strip() if surname is not None and surname.text else ""
            )

            # Combine cleanly based on available strings
            full_name = f"{given_text} {surname_text}".strip()
            if full_name:
                authors.append(full_name)

        # Resolve associated Attachments via the resource link references
        attachments = []
        for link in article.findall("link:link", ns):
            resource_attr = link.get(f"{{{ns['rdf']}}}resource", "")
            link_id = resource_attr.lstrip("#")
            if link_id in attachment_map:
                attachments.append(attachment_map[link_id])

        # Instantiate structural dataclass
        documents.append(
            Document(
                id=len(documents),
                zid=doc_id,
                title=title,
                authors=tuple(authors),
                attachments=tuple(attachments),
            )
        )

    return documents


if __name__ == "__main__":
    import argparse
    import random

    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="path to the RDF file")
    args = parser.parse_args()

    docs = load_rdf(args.file)
    doc = random.choice(docs)
    print(f"#items: {len(docs)}")
    print(f"#attachments: {sum(len(d.attachments) for d in docs)}")
    print(f"random sample: {doc}")

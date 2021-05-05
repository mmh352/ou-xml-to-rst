"""Functionality to convert an OU-XML document into a RST tree."""
import click
import shutil
import os

from lxml import etree
from importlib import resources


DEFAULT_BLOCK = None
DEFAULT_PART = None
DEFER_OUTPUT = []
MATH_XSLT = None


def fix_trailing_space(node: etree.Element):
    """Fix trailing spaces, moving them into the node's tail."""
    if node.text and node.text.endswith(' '):
        node.text = node.text[:-1]
        if node.tail:
            node.tail = f' {node.tail}'
        else:
            node.tail = ' '



def process_node(node: etree.Element, indent: str='') -> list:
    """Process a node."""
    global DEFER_OUTPUT

    if node.tag == 'Title':
        title_text = [node.text]
        if len(node) > 0:
            for child in node:
                title_text.extend(process_node(child))
        title_text = ''.join(title_text).strip()
        heading_char = '#'
        return [title_text, heading_char * len(title_text), '']
    elif node.tag == 'Paragraph':
        buffer = [indent]
        if node.text:
            buffer.append(node.text)
        for child in node:
            buffer.extend(process_node(child))
        return [''.join(buffer), '']
    elif node.tag == 'Box':
        heading_text = node.xpath('Heading/text()')
        if heading_text:
            buffer = [f'{indent}.. admonition:: {heading_text[0]}', '']
        for child in node:
            if child.tag != 'Heading':
                buffer.extend(process_node(child, indent=f'{indent}    '))
        if buffer[-1] != '':
            buffer.append('')
        return buffer
    elif node.tag == 'StudyNote':
        buffer = [f'{indent}.. note::', '']
        for child in node:
            buffer.extend(process_node(child, indent=f'{indent}    '))
        return buffer
    elif node.tag == 'Image':
        if 'src' in node.attrib:
            filename = node.attrib['src'][node.attrib['src'].rfind('\\') + 1:]
            return [f'.. image:: {filename}', '']
    elif node.tag == 'Figure':
        filename = node.xpath('Image/@src')
        if filename:
            filename = filename[0][filename[0].rfind('\\') + 1:]
            buffer = [f'{indent}.. figure:: {filename}', '']
            caption = node.xpath('Caption')
            if caption:
                tmp = [f'{indent}    ']
                if caption[0].text:
                    tmp.append(caption[0].text)
                for child in caption[0]:
                    tmp.append(process_node(child))
                buffer.append(''.join(tmp))
                buffer.append('')
            return buffer
    elif node.tag == 'MediaContent':
        if 'src' in node.attrib:
            if node.attrib['src'].startswith('youtube:'):
                buffer = [f'{indent}.. youtube:: {node.attrib["src"][8:]}', '']
                description = node.xpath('Description')
                if description:
                    buffer.extend(process_node(description[0], indent=f'{indent}    '))
                transcript = node.xpath('Transcript')
                if transcript:
                    buffer.extend(process_node(transcript[0], indent=f'{indent}    '))
                return buffer
            else:
                filename = node.attrib['src'][node.attrib['src'].rfind('\\') + 1:]
                buffer = [f'{indent}.. iframe:: {filename}']
                if 'width' in node.attrib:
                    buffer.append(f'{indent}    :width: {node.attrib["width"]}')
                if 'height' in node.attrib:
                    buffer.append(f'{indent}    :height: {node.attrib["height"]}')
                buffer.append('')
                caption = node.xpath('Caption')
                if caption:
                    for child in caption[0]:
                        buffer.extend(process_node(child, indent=indent))
                if buffer[-1] != '':
                    buffer.append('')
                return buffer
    elif node.tag == 'Description':
        buffer = [f'{indent}.. description::', '']
        for child in node:
            buffer.extend(process_node(child, indent=f'{indent}    '))
        return buffer
    elif node.tag == 'Transcript':
        buffer = [f'{indent}.. transcript::', '']
        for child in node:
            buffer.extend(process_node(child, indent=f'{indent}    '))
        return buffer
    elif node.tag == 'Activity':
        heading_text = node.xpath('Heading/text()')
        if heading_text:
            buffer = [f'{indent}.. activity:: {heading_text[0]}', '']
            for child in node:
                if child.tag != 'Heading':
                    buffer.extend(process_node(child, indent=f'{indent}    '))
            return buffer
    elif node.tag == 'Question':
        buffer = []
        for child in node:
            buffer.extend(process_node(child, indent=f'{indent}'))
        return buffer
    elif node.tag == 'Answer':
        buffer = [f'{indent}.. activity-answer::', '']
        for child in node:
            buffer.extend(process_node(child, indent=f'{indent}    '))
        return buffer
    elif node.tag == 'Quote':
        buffer = []
        for child in node:
            buffer.extend(process_node(child, indent=f'{indent}    '))
        return buffer
    elif node.tag == 'SourceReference':
        buffer = [f'{indent}-- ']
        if node.text:
            buffer.append(node.text)
        for child in node:
            buffer.extend(process_node(child))
        return [''.join(buffer), '']
    elif node.tag == 'Reference':
        if node.text:
            buffer = [f'.. [{node.text.strip()}] {node.text}']
            for child in node:
                buffer.extend(process_node(child))
            return [''.join(buffer), '']
    elif node.tag in ['BulletedList', 'BulletedSubsidiaryList', 'UnNumberedList', 'NumberedList']:
        buffer = []
        for child in node:
            buffer.extend(process_node(child, indent=indent))
        if buffer[-1] != '':
            buffer.append('')
        return buffer
    elif node.tag in ['ListItem', 'SubListItem']:
        item_tag = '* '
        if node.getparent().tag in ['NumberedList']:
            item_tag = '#. '
        if node.text:
            buffer = [f'{indent}{item_tag}{node.text}']
            for child in node:
                buffer.extend(process_node(child))
            return [''.join(buffer)]
        else:
            buffer = []
            for idx, child in enumerate(node):
                if idx == 0:
                    buffer.extend(process_node(child, indent=f'{indent}{item_tag}'))
                else:
                    buffer.extend(process_node(child, indent=f'{indent}{" " * len(item_tag)}'))
            return buffer
    elif node.tag == 'ComputerCode':
        if '\n' in node.text:
            buffer = [f'{indent}.. sourcecode::', '']
            buffer.extend([f'{indent}    {line}' for line in node.text.split('\n')])
            return ['\n'.join(buffer)]
        else:
            fix_trailing_space(node)
            buffer = []
            if node.text:
                buffer.append(f'``{node.text}``')
            if node.tail:
                buffer.append(node.tail)
            return buffer
    elif node.tag == 'Equation':
        math = MATH_XSLT(node.xpath('MathML')[0])
        if math:
            latex = bytes(math).decode().\
                replace('\n', '').replace('\\[', '$$').replace('\\]', '$$').replace('\\', '\\\\')
            return [f'{indent}{latex}', '']
    elif node.tag == 'i':
        buffer = []
        if node.text:
            fix_trailing_space(node)
            buffer.append(f'*{node.text}*')
        if node.tail:
            buffer.append(node.tail)
        return buffer
    elif node.tag == 'b':
        buffer = []
        if node.text:
            fix_trailing_space(node)
            buffer.append(f'**{node.text}**')
        if node.tail:
            buffer.append(node.tail)
        return buffer
    elif node.tag == 'a':
        buffer = []
        if node.text and 'href' in node.attrib:
            fix_trailing_space(node)
            buffer.append(f'`{node.text} <{node.attrib["href"]}>`_')
        if node.tail:
            buffer.append(node.tail)
        return buffer
    elif node.tag == 'olink':
        buffer = []
        if node.text and 'targetdoc' in node.attrib:
            fix_trailing_space(node)
            target = [part.strip().lower().replace(' ', '') for part in node.attrib['targetdoc'].split(',')]
            if len(target) == 0 or not target[0].startswith('block'):
                if len(target) == 0 or not target[0].startswith('part'):
                    target.insert(0, DEFAULT_PART)
                target.insert(0, DEFAULT_BLOCK)
            buffer.append(f':doc:`{node.text} </{"/".join(target)}/index>`')
        if node.tail:
            buffer.append(node.tail)
        return buffer
    elif node.tag == 'InlineFigure':
        buffer = []
        imagesrc = node.xpath('Image/@src')
        if imagesrc:
            imageid = imagesrc[0][imagesrc[0].rfind('\\') + 1:]
            buffer.append(f'|{imageid}|')
            tmp = process_node(node.xpath('Image')[0])
            if tmp:
                tmp[0] = f'.. |{imageid}|{tmp[0][2:]}'
                DEFER_OUTPUT.extend(tmp)
        if node.tail:
            buffer.append(node.tail)
        return buffer
    elif node.tag in ['Section']:
        pass
    else:
        print(node.tag)
    return []


def process_section(idx, section, dest):
    """Process a section level node."""
    global DEFER_OUTPUT

    filename = os.path.join(dest, f'section{idx + 1}/index.rst')
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    buffer = []
    DEFER_OUTPUT = []
    for node in section:
        buffer.extend(process_node(node))

    if DEFER_OUTPUT:
        buffer.extend(DEFER_OUTPUT)

    with open(filename, 'w') as out_f:
        for line in buffer:
            print(line, file=out_f)


def process_session(idx, session, dest):
    """Process a session level node."""
    global DEFER_OUTPUT

    filename = os.path.join(dest, f'session{idx + 1}/index.rst')
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    buffer = []
    DEFER_OUTPUT = []
    for node in session:
        buffer.extend(process_node(node))

    sections = session.xpath('Section')
    if sections:
        buffer.append('.. toctree::')
        buffer.append('    :maxdepth: 1')
        buffer.append('    :hidden:')
        buffer.append('')
        for section_idx, section in enumerate(sections):
            process_section(section_idx, section, os.path.join(dest, f'session{idx + 1}'))
            buffer.append(f'    section{section_idx + 1}/index')

    if DEFER_OUTPUT:
        buffer.extend(DEFER_OUTPUT)

    with open(filename, 'w') as out_f:
        for line in buffer:
            print(line, file=out_f)


@click.command()
@click.argument('src', type=click.File())
@click.argument('dest', type=click.Path())
@click.option('-b', '--block', type=int, required=True)
@click.option('-p', '--part', type=int, required=True)
def run_import(src, dest, block, part):
    """Import a unit from a StructureContent document."""
    global DEFAULT_BLOCK, DEFAULT_PART, MATH_XSLT
    DEFAULT_BLOCK = f'block{block}'
    DEFAULT_PART = f'part{part}'
    with resources.path('ou_xml_to_rst.xsltml', 'mmltex.xsl') as filepath:
        MATH_XSLT = etree.XSLT(etree.parse(str(filepath)))

        if (os.path.exists(dest)):
            shutil.rmtree(dest)

        buffer = [
            os.path.basename(dest),
            '#' * len(os.path.basename(dest)),
            '',
            '.. toctree::',
            '    :maxdepth: 1',
            '    :hidden:',
            ''
        ]

        doc = etree.parse(src, parser=etree.XMLParser(remove_pis=True))
        for idx, session in enumerate(doc.xpath('Unit/Session')):
            process_session(idx, session, dest)
            buffer.append(f'    session{idx + 1}/index')

        with open(os.path.join(dest, 'index.rst'), 'w') as out_f:
            for line in buffer:
                print(line, file=out_f)


if __name__ == '__main__':
    run_import()

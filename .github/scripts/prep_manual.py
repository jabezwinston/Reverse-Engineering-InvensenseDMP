"""Rewrite docs/manual for the Jekyll (kramdown) build; run in CI on the checkout only.

The manual tags its listings ```asm both / ```asm mpu6050 / ```asm icm20948 for
tools/manual_check.py.  kramdown accepts only one word after the fence, so it renders
those blocks as paragraphs.  Here each becomes ```nasm: Rouge, the highlighter GitHub
Pages provides, has no lexer for DMP assembly, and its NASM lexer is the closest
(";" comments, labels, hex and decimal numbers).

Each page also gets a sidebar (styled in _includes/head-custom.html): every chapter,
with the current one expanded into its sections (x.y) by kramdown's {:toc}.
"""
import pathlib
import re
import sys

OPEN = re.compile(r"^(\s*)```asm\s+(\S+)\s*$")

pages = sorted(pathlib.Path(sys.argv[1]).glob("*.md"))
chapters = [p for p in pages if p.name != "README.md"]
titles = {p.name: p.read_text().split("\n", 1)[0].lstrip("# ").strip() for p in chapters}


def sidebar(current):
    md = ['<nav id="sidebar" markdown="1">', ""]
    md.append("**Contents**" if current == "README.md" else "[Contents](README.md)")
    md.append("{:.sb-home}")
    md.append("")
    for p in chapters:
        num, _, name = titles[p.name].partition(". ")
        if p.name == current:
            md += [f"- {num}\\. **{name}**", "", "  * TOC", "  {:toc}", ""]
        else:
            md += [f"- {num}\\. [{name}]({p.name})"]
    md += ["", "</nav>", ""]
    return md


for path in pages:
    out, chip, indent, n = [], None, "", 0
    lines = path.read_text().splitlines()
    # the sidebar goes straight after the page's "# " title
    out += [lines[0], ""] + sidebar(path.name)
    for line in lines[1:]:
        m = OPEN.match(line)
        if chip is None and m:
            indent, chip = m.group(1), m.group(2)
            out.append(f"{indent}```nasm")
            continue
        out.append(line)
        if chip is not None and line.strip() == "```":
            chip, n = None, n + 1
    if chip is not None:
        sys.exit(f"{path}: unclosed ```asm block")
    path.write_text("\n".join(out) + "\n")
    if n:
        print(f"{path.name}: {n} asm blocks")

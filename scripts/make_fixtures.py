"""Build the sample inputs for the end-to-end run: lecture notes and a photographed answer booklet.

    python scripts/make_fixtures.py OUT_DIR
"""
import io
import os
import sys

import fitz
from PIL import Image, ImageDraw, ImageFilter, ImageFont

NOTES = [
    "Chapter 1 Neural Networks\nA neural network is built from layers of neurons. Each neuron computes a weighted sum of its inputs and applies an activation function. "
    "Backpropagation computes gradients of the loss with respect to every weight using the chain rule. Gradient descent then updates the weights in proportion to the learning rate.",
    "Chapter 2 Convolutional Neural Networks\nA convolutional neural network applies learned convolution filters to the input image to produce feature maps. "
    "Pooling layers downsample feature maps, which reduces computation and adds tolerance to small shifts. A fully connected layer at the end turns the features into class scores.",
]
ANSWERS = [
    "Page 1\nQ1. A convolutional neural network applies\nconvolution filters to the input image to make\nfeature maps. Pooling layers downsample the\nfeature maps to reduce computation.",
    "Page 2\nA fully connected layer gives the class scores.\nQ2. Each neuron computes a weighted sum and\napplies an activation function. Backpropagation\nuses the chain rule to get gradients.",
]


def notes_pdf() -> bytes:
    doc = fitz.open()
    for body in NOTES:
        doc.new_page().insert_textbox(fitz.Rect(50, 50, 545, 800), body, fontsize=11)
    return doc.tobytes()


def booklet_pdf() -> bytes:
    font = next((ImageFont.truetype(p, 30) for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",) if os.path.exists(p)), None) or ImageFont.load_default(size=30)
    doc = fitz.open()
    for body in ANSWERS:
        img = Image.new("RGB", (1240, 1754), (250, 248, 240))
        d = ImageDraw.Draw(img)
        for i, line in enumerate(body.splitlines()):
            d.text((90, 80 + i * 52), line, fill=(20, 30, 120), font=font)
        img = img.rotate(1.2, fillcolor=(250, 248, 240)).filter(ImageFilter.GaussianBlur(0.6))
        buf = io.BytesIO(); img.save(buf, "JPEG", quality=85)
        p = doc.new_page(width=595, height=842)
        p.insert_image(p.rect, stream=buf.getvalue())
    return doc.tobytes()


if __name__ == "__main__":
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, "ml-notes.pdf"), "wb").write(notes_pdf())
    open(os.path.join(out, "answer-booklet.pdf"), "wb").write(booklet_pdf())
    print(out)

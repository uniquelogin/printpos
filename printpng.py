#!/usr/bin/env python3

import usb.core
import usb.util
from PIL import Image
import PIL
import time

DEF_TOTAL_HEIGHT_LIMIT = 3000  # pixels
PRINT_WIDTH = 512  # px
STRIPE_HEIGHT = 32  # px

# Cool down the print head to avoid smearing
COOLDOWN_EVERY = 1000  # pixel lines
COOLDOWN_TIME = 1.5  # sec

def get_usb_endpoint():
    # find our device
    dev = usb.core.find(idVendor=0x0519, idProduct=0x000b)

    dev.set_configuration()

    cfg = dev.get_active_configuration()
    intf = cfg[(0,0)]

    ep = usb.util.find_descriptor(
        intf,
        # match the first OUT endpoint
        custom_match = \
        lambda e: \
            usb.util.endpoint_direction(e.bEndpointAddress) == \
            usb.util.ENDPOINT_OUT)

    return ep


class BitStripe(object):
    def __init__(self, width, height):
        assert width % 8 == 0

        self.width = width
        self.height = height
        self.byte_width = self.width // 8
        self.array = bytearray(self.byte_width * self.height)
        assert len(self.array) <= 4096
        self.pos = 0
        self.num_pixels = self.width * self.height

    def push(self, value):
        assert(self.pos < self.num_pixels)
        if value:
            val = 0x01 << (7 - self.pos % 8)
            self.array[self.pos // 8] += val
        self.pos += 1

def send_image(outf, im, vlimit):
    stripe = None

    total_height = min(im.size[1], vlimit)
    remaining_height = total_height
    cooldown_counter = 0

    width = im.size[0]
    width_pad = im.size[0] % 8
    if width_pad:
        width_pad = 8 - width_pad

    for y in range(total_height):
        if not stripe:
            height = remaining_height
            if height > STRIPE_HEIGHT:
                height = STRIPE_HEIGHT
            remaining_height -= height
            end_y = y + height - 1
            stripe = BitStripe(width + width_pad, height)
        for x in range(width):
            stripe.push(0 if im.getpixel((x, y)) else 1)
        for x in range(width_pad):
            stripe.push(0)
        if y == end_y:
            outf.write(bytes([0x1d, 0x76, 0x30, 0x30, stripe.byte_width, 0x00, stripe.height, 0x00]))
            outf.write(stripe.array)
            cooldown_counter += stripe.height
            if cooldown_counter > COOLDOWN_EVERY:
                time.sleep(1.0)
                cooldown_counter = 0
            stripe = None

    outf.write(b'\x0a\x1d\x56\x41\x01')

def main():
    import argparse
    import sys

    argparser = argparse.ArgumentParser()
    argparser.add_argument('--vlimit', type=int, default=DEF_TOTAL_HEIGHT_LIMIT, help='Image height limit in pixels')
    argparser.add_argument('--width', type=int, default=PRINT_WIDTH, help='Desired image width in pixels')
    argparser.add_argument('--noedit', default=False, action='store_true', help='Don\'t rotate/rescale the image')
    argparser.add_argument('image_file')
    args = argparser.parse_args()

    ep = get_usb_endpoint()
    im = Image.open(args.image_file)
    print('Image:', im.format, im.size, im.mode, im.getbands(), file=sys.stderr)
    if not args.noedit and im.size[0] > im.size[1] and im.size[0] > args.width:
        im = im.rotate(angle=90, expand=True)
    if im.getbands() != ('1'):
        if im.size[0] != args.width and not args.noedit:
            im = im.resize((args.width, int(im.size[1] * args.width/im.size[0])), resample=PIL.Image.LANCZOS)
        im = im.convert('1')
    print('Converted:', im.format, im.size, im.mode, file=sys.stderr)
    assert len(im.getbands()) == 1
    
    send_image(ep, im, args.vlimit)
    return True

if __name__ == '__main__':
    if not main():
        sys.exit(1)


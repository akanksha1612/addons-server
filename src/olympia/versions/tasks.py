import tempfile
import os
import subprocess
from base64 import b64encode

from django.conf import settings
from django.core.files.storage import default_storage as storage
from django.template import loader


import olympia.core.logger
from olympia import amo
from olympia.amo.celery import task
from olympia.amo.decorators import write


log = olympia.core.logger.getLogger('z.files.utils')


def write_svg_to_png(svg_content, target):
    tmp_args = {'dir': settings.TMP_PATH, 'mode': 'wb', 'suffix': '.svg'}
    with tempfile.NamedTemporaryFile(**tmp_args) as temporary_svg:
        temporary_svg.write(svg_content)
        temporary_svg.flush()

        size = None
        try:


            command = [
                settings.RSVG_CONVERT_BIN,
                '-o', target,
                temporary_svg.name
            ]
            print('XXXXXXX', command)
            subprocess.call(command)

            # TODO: update size
            size = None
        except IOError as ioerror:
            log.debug(ioerror)
    return size


@task
@write
def generate_static_theme_preview(theme_manifest, header_root, preview):
    tmpl = loader.get_template(
        'devhub/addons/includes/static_theme_preview_svg.xml')
    context = {'amo': amo}
    context.update(theme_manifest.get('colors', {}))
    header_url = theme_manifest.get('images', {}).get('headerURL')

    header_path = os.path.join(header_root, header_url)
    try:
        with storage.open(header_path, 'rb') as header_file:
            header_blob = header_file.read()
            with WandImage(blob=header_blob) as header_image:
                (width, height) = header_image.size
                context.update(header_src_height=height)
                meetOrSlice = ('meet' if width < amo.THEME_PREVIEW_SIZE.width
                               else 'slice')
                context.update(
                    preserve_aspect_ratio='xMaxYMin %s' % meetOrSlice)
                data_url = 'data:%s;base64,%s' % (
                    header_image.mimetype, b64encode(header_blob))
                context.update(header_src=data_url)
    except IOError as io_error:
        log.debug(io_error)
    except WandException as wand_exception:
        log.debug(wand_exception)

    svg = tmpl.render(context).encode('utf-8')
    size = write_svg_to_png(svg, preview.image_path)
    if size:
        preview.update(sizes={'image': size})

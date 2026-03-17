import os
import uuid

from django.conf import settings
def save_temp_upload(django_file, prefix: str) -> str:
    if not django_file:
        return ""
    
    base_dir = os.path.join(settings.MEDIA_ROOT, "tmp_imports")
    os.makedirs(base_dir, exist_ok=True)

    path = os.path.join(base_dir, f"{prefix}_{uuid.uuid4().hex}_{django_file.name}")
    with open(path, "wb+") as f:
        for chunk in django_file.chunks():
            f.write(chunk)
    return path
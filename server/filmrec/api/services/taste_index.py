#api/services/taste_index.py
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from openai import OpenAI
from django.contrib.auth import get_user_model

User = get_user_model()

DELETE_WORKERS = 10

def _delete_store_file(client: OpenAI, store_id: str, file_id: str) -> str:
    # Delete a single vector store file. 
    # Returns the file_id on success
    client.vector_stores.files.delete(
        vector_store_id=store_id,
        file_id=file_id,
    )
    return file_id

def get_or_create_taste_vector_store(
        *,
        user,
        client: OpenAI | None = None,
        name_prefix: str = "FilmRec Taste Store",
) -> str:
    # Return the user's taste vector store id, creatig it if needed
    client = client or OpenAI()
    store_id = getattr(user, "taste_vector_store_id", None)

    if store_id:
        return store_id
    
    vs = client.vector_stores.create(name=f"{name_prefix} (user={user.id})")
    store_id = vs.id
    user.taste_vector_store_id = store_id
    user.save(update_fields=["taste_vector_store_id"])
    return store_id

def clear_taste_vector_store_files(
        *,
        store_id: str,
        client: OpenAI | None = None,
        max_workers: int = DELETE_WORKERS,
) -> int:
    # Delete all files currently attached to the user's taste vector store
    # returns the number of deleted files
    client = client or OpenAI()

    try:
        existing = client.vector_stores.files.list(vector_store_id=store_id)
        file_ids = [vf.id for vf in existing.data]
    except Exception as e:
        raise RuntimeError(f"Failed listing existing taste store files: {e}")
    
    if not file_ids:
        return 0
    
    failed: list[tuple[str, str]] = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_delete_store_file, client, store_id, fid): fid
            for fid in file_ids
        }

        for future in as_completed(futures):
            fid = futures[future]
            try:
                future.result()
            except Exception as exc:
                failed.append((fid, str(exc)))

    if failed:
        raise RuntimeError(f"Failed to delete {len(failed)} file(s)")
    
    return len(file_ids)

def upload_taste_file_to_store(
        *,
        store_id: str,
        file_path: str | Path,
        client: OpenAI | None = None,
):
    # Upload the user's taste file to the vector store and wait until indexing completes
    # Returns the SDK response from upload and poll
    client = client or OpenAI()
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Missing taste file: {file_path}")
    
    try:
        with file_path.open("rb") as f:
            return client.vector_stores.files.upload_and_poll(
                vector_store_id=store_id,
                file=f,
            )
    except Exception as e:
        raise RuntimeError(f"Upload failed: {e}")

def ensure_taste_indexed(
        *,
        user_id: int,
        file_path: str | Path,
        name_prefix: str = "FilmRec Taste Store",
        clear_existing: bool = True,
        client: OpenAI | None = None,
) -> dict:
    """
    Full reusable indexing flow:
        - resolve user
        - get/create taste vector store
        - optionally clear old files
        - upload latest taste file
    """
    client = client or OpenAI()

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        raise RuntimeError(f"User {user_id} not found.")
    
    store_id = get_or_create_taste_vector_store(
        user=user,
        client=client,
        name_prefix=name_prefix,
    )

    deleted_count = 0
    if clear_existing:
        deleted_count = clear_taste_vector_store_files(
            store_id=store_id,
            client=client,
        )

    upload_result = upload_taste_file_to_store(
        store_id=store_id,
        file_path=file_path,
        client=client,
    )

    return {
        "user_id": user.id,
        "store_id": store_id,
        "file_path": str(Path(file_path)),
        "deleted_count": deleted_count,
        "upload_result": upload_result,
    }



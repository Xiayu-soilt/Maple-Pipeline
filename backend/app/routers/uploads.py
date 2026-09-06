import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Upload

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
MAX_SIZE_MB = 50

ALLOWED_SUFFIXES = {
    ".zip", ".py", ".txt", ".md", ".json", ".yaml", ".yml", ".toml",
    ".cfg", ".ini", ".js", ".ts", ".html", ".css", ".sql", ".sh", ".bat",
}


def _is_safe_member(name: str) -> bool:
    return not name.startswith(("/", "\\")) and ".." not in name.replace("\\", "/")


@router.post("")
async def create_upload(file: UploadFile = File(...), db: Session = Depends(get_db)):
    name = file.filename or "upload.zip"
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(400, f"不支持的文件类型 {suffix}，请上传 zip 压缩包或常见代码/文本文件")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored = UPLOAD_DIR / f"{uuid.uuid4().hex[:12]}_{Path(name).name}"
    size = 0
    try:
        with stored.open("wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_SIZE_MB * 1024 * 1024:
                    raise HTTPException(400, f"文件超过 {MAX_SIZE_MB}MB 限制")
                f.write(chunk)

        file_count = 1
        if suffix == ".zip":
            try:
                with zipfile.ZipFile(stored) as zf:
                    members = zf.infolist()
            except zipfile.BadZipFile:
                raise HTTPException(400, "zip 文件损坏或不是有效的压缩包")
            bad = [m.filename for m in members if not _is_safe_member(m.filename)]
            if bad:
                raise HTTPException(400, f"压缩包内含非法路径（疑似 zip slip 攻击）: {bad[0]}")
            file_count = sum(1 for m in members if not m.is_dir())
            if file_count == 0:
                raise HTTPException(400, "压缩包内没有文件")
    except HTTPException:
        stored.unlink(missing_ok=True)
        raise
    except Exception as e:
        stored.unlink(missing_ok=True)
        raise HTTPException(400, f"上传失败: {e}")

    up = Upload(filename=name, stored_path=str(stored),
                size_kb=round(size / 1024), file_count=file_count)
    db.add(up)
    db.commit()
    db.refresh(up)
    return {"id": up.id, "filename": up.filename, "size_kb": up.size_kb, "file_count": up.file_count}


@router.get("")
def list_uploads(db: Session = Depends(get_db)):
    return [
        {"id": u.id, "filename": u.filename, "size_kb": u.size_kb,
         "file_count": u.file_count, "created_at": u.created_at}
        for u in db.query(Upload).order_by(Upload.id.desc()).limit(50).all()
    ]

import json as _json

# ---- schemas.py: add FacialEmbeddingIn and EnrolledFaceOut ----
with open('schemas.py') as f:
    schemas_content = f.read()

changed_schemas = False

if 'class FacialEmbeddingIn' not in schemas_content:
    schemas_content += (
        "\n\nclass FacialEmbeddingIn(BaseModel):\n"
        "    embedding: List[float]\n"
    )
    changed_schemas = True
    print('schemas.py: FacialEmbeddingIn added')
else:
    print('schemas.py: FacialEmbeddingIn already present, skipped')

if 'class EnrolledFaceOut' not in schemas_content:
    schemas_content += (
        "\n\nclass EnrolledFaceOut(BaseModel):\n"
        "    evacuee_id: int\n"
        "    full_name: str\n"
        "    embedding: List[float]\n"
    )
    changed_schemas = True
    print('schemas.py: EnrolledFaceOut added')
else:
    print('schemas.py: EnrolledFaceOut already present, skipped')

if changed_schemas:
    with open('schemas.py', 'w') as f:
        f.write(schemas_content)
    print('schemas.py: saved')

# ---- main.py: add import json, and the two new endpoints ----
with open('main.py') as f:
    main_content = f.read()

changed_main = False

if 'import json' not in main_content:
    main_content = 'import json\n' + main_content
    changed_main = True
    print('main.py: import json added')
else:
    print('main.py: import json already present, skipped')

if '/evacuees/{evacuee_id}/facial_embedding' not in main_content:
    addition = (
        '\n\n'
        '@app.post("/evacuees/{evacuee_id}/facial_embedding")\n'
        'def set_facial_embedding(evacuee_id: int, payload: schemas.FacialEmbeddingIn, db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):\n'
        '    evacuee = db.query(models.Evacuee).filter(models.Evacuee.id == evacuee_id).first()\n'
        '    if not evacuee:\n'
        '        raise HTTPException(status_code=404, detail="Evacuee not found")\n'
        '    evacuee.facial_embedding = json.dumps(payload.embedding)\n'
        '    evacuee.identification_method = "facial_recognition"\n'
        '    db.commit()\n'
        '    return {"evacuee_id": evacuee_id, "status": "embedding saved"}\n'
    )
    main_content += addition
    changed_main = True
    print('main.py: POST /evacuees/{evacuee_id}/facial_embedding added')
else:
    print('main.py: facial_embedding endpoint already present, skipped')

if '/evacuees/enrolled_faces' not in main_content:
    addition = (
        '\n\n'
        '@app.get("/evacuees/enrolled_faces", response_model=list[schemas.EnrolledFaceOut])\n'
        'def enrolled_faces(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):\n'
        '    evacuees = db.query(models.Evacuee).filter(models.Evacuee.facial_embedding.isnot(None)).all()\n'
        '    result = []\n'
        '    for e in evacuees:\n'
        '        try:\n'
        '            embedding = json.loads(e.facial_embedding)\n'
        '        except (TypeError, ValueError):\n'
        '            continue\n'
        '        result.append({"evacuee_id": e.id, "full_name": e.full_name, "embedding": embedding})\n'
        '    return result\n'
    )
    main_content += addition
    changed_main = True
    print('main.py: GET /evacuees/enrolled_faces added')
else:
    print('main.py: enrolled_faces endpoint already present, skipped')

if changed_main:
    with open('main.py', 'w') as f:
        f.write(main_content)
    print('main.py: saved')

print('DONE')

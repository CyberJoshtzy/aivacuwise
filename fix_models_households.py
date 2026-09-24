with open('models.py') as f:
    models_content = f.read()

old_tail = '    identification_method = Column(String, nullable=True, default="manual")'
new_tail = old_tail + '\n    household_id = Column(Integer, ForeignKey("households.id"), nullable=True)\n    is_head_of_family = Column(Boolean, nullable=True, default=False)'

if 'household_id = Column' not in models_content:
    count = models_content.count(old_tail)
    if count == 1:
        models_content = models_content.replace(old_tail, new_tail, 1)
        print('models.py: household_id/is_head_of_family added to Evacuee')
    else:
        print('models.py: WARNING expected exactly 1 match for identification_method line, found', count, '- skipped')
else:
    print('models.py: household_id already present, skipped')

dunder = '_' * 2
household_class = (
    "\n\nclass Household(Base):\n"
    "    " + dunder + "tablename" + dunder + ' = "households"\n'
    "    id = Column(Integer, primary_key=True)\n"
    "    registered_barangay_id = Column(Integer, ForeignKey(\"barangays.id\"), nullable=False)\n"
    "    head_of_family_evacuee_id = Column(Integer, ForeignKey(\"evacuees.id\"), nullable=True)\n"
    "    created_at = Column(DateTime, default=datetime.utcnow)\n"
)

if 'class Household(Base)' not in models_content:
    models_content += household_class
    print('models.py: Household class appended')
else:
    print('models.py: Household class already present, skipped')

with open('models.py', 'w') as f:
    f.write(models_content)

print('DONE')

from pathlib import Path
import shutil

path = Path('tests/test_mini_crm.py')
if not path.exists():
    raise SystemExit('ERROR: Run from Food_Porn project root.')
text = path.read_text(encoding='utf-8')
old = 'async def test_vip_can_read_crm_and_legacy_admin_but_not_change_access(crm):\n    header = signed(12, "vipperson")\n    assert (await crm.client.get("/crm/api/dashboard", headers=header)).status_code == 200\n    assert (await crm.client.get("/miniapp/api/admin", headers=header)).status_code == 200\n'
new = 'async def test_vip_cannot_read_crm_or_change_access(crm):\n    header = signed(12, "vipperson")\n    assert (await crm.client.get("/crm/api/dashboard", headers=header)).status_code == 403\n'
if old not in text:
    if 'async def test_vip_cannot_read_crm_or_change_access' in text:
        print('Already patched; no changes made.')
        raise SystemExit(0)
    raise SystemExit('ERROR: Exact old test block not found; no changes made. Send current test file.')
if 'async def test_owner_can_read_crm_dashboard' not in text:
    new += '\n\nasync def test_owner_can_read_crm_dashboard(crm):\n    assert (await crm.client.get("/crm/api/dashboard", headers=signed(42))).status_code == 200\n'
    # Insert the new test after the existing test function, before the next function.
    start = text.index(old)
    next_test = text.find('\nasync def test_', start + len(old))
    if next_test < 0:
        raise SystemExit('ERROR: Next test boundary not found; no changes made.')
    # Preserve original assertions, insert owner test after this test.
    text = text.replace(old, new.split('\n\nasync def test_owner_can_read_crm_dashboard')[0], 1)
    next_test = text.find('\nasync def test_', start + len(new))
    text = text[:next_test] + '\n\nasync def test_owner_can_read_crm_dashboard(crm):\n    assert (await crm.client.get("/crm/api/dashboard", headers=signed(42))).status_code == 200\n' + text[next_test:]
else:
    text = text.replace(old, new, 1)
backup = path.with_suffix('.py.before_v4.bak')
shutil.copy2(path, backup)
path.write_text(text, encoding='utf-8')
print('Patched:', path)
print('Backup:', backup)
print('Old test remains:', 'async def test_vip_can_read_crm_and_legacy_admin_but_not_change_access' in text)

# Data

## Collections

```python
from rn_forge.commons import DictUtils, ListUtils

data = {"users": [{"name": "Alice"}, {"name": "Bob"}]}
name = DictUtils.get(data, "users.1.name")
grouped = ListUtils.group_by(["aa", "ab", "ba"], key_fn=lambda item: item[0])
```

`get` returns `Any`. To read a parsed TOML/YAML/JSON document under a strict type
checker, use the typed reads instead. They never raise: a missing path or a
value of the wrong shape reads as empty (or the given default).

```python
doc = {"tasks": {"build": {"cmds": "echo hi"}}, "dev": ["pytest", {"include-group": "lint"}]}

DictUtils.get_mapping(doc, "tasks.build")      # {"cmds": "echo hi"}  (dict[str, object])
DictUtils.get_list(doc, "tasks.build.cmds")    # ["echo hi"]  a lone scalar is one element
DictUtils.get_strings(doc, "dev")              # ["pytest"]   non-strings dropped
DictUtils.get_str(doc, "tasks.build.cmds")     # "echo hi"
DictUtils.get_bool(doc, "strict", default=True)  # True
```

## Documents

`JsonUtils` and `YamlUtils` cover plain (de)serialization and file I/O.
`DocumentUtils` dispatches on a path's suffix and can edit TOML/YAML in place
without losing comments or formatting.

```python
from rn_forge.commons import DocumentUtils, JsonUtils, YamlUtils

text = JsonUtils.serialize(grouped, indent=2)
yaml_text = YamlUtils.serialize(data)

# comments and formatting in pyproject.toml survive this edit
DocumentUtils.update("pyproject.toml", {"project": {"version": "0.4.0"}})
```

## Dataclasses

```python
from dataclasses import dataclass

from rn_forge.commons import DataclassMixin

@dataclass
class User(DataclassMixin):
    name: str
    active: bool = True

user = User.from_dict({"name": "Alice"})
payload = user.to_json()
```

`from_dict()` is strict: `User.from_dict({"name": "Alice", "active": "yes"})`
raises `AppException: Invalid User: wrong value type for field "active"`.
Subclass `LenientDataclassMixin` for the record that wants the value through
instead — and see that class's docstring for the two annotations dacite cannot
check, which force the same choice.

Unknown keys are ignored by default. Subclass `StrictDataclassMixin` for a
document whose author should hear about a typo: it rejects any key that names
no field, in nested sections too — whether or not the nested section's own
class is strict, since strictness belongs to the document being read — and
names each one by its dotted path —
`AppException: Invalid ProjectConfig: unknown key(s) repository.archtype`.

## Pandas and Excel

```python
from rn_forge.commons.data.excel import ExcelAdapter, ExcelUtils

frames = ExcelAdapter.read_dataframe("orders.xlsx")
workbook = ExcelAdapter.from_dataframe(frames)
ExcelUtils.write_workbook(workbook, "build/orders-copy.xlsx")
```

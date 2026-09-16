# Data

## Collections

```python
from rn_forge.commons import DictUtils, ListUtils

data = {"users": [{"name": "Alice"}, {"name": "Bob"}]}
name = DictUtils.get(data, "users.1.name")
grouped = ListUtils.group_by(["aa", "ab", "ba"], key_fn=lambda item: item[0])
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

## Pandas and Excel

```python
from rn_forge.commons.data.excel import ExcelAdapter, ExcelUtils

frames = ExcelAdapter.read_dataframe("orders.xlsx")
workbook = ExcelAdapter.from_dataframe(frames)
ExcelUtils.write_workbook(workbook, "build/orders-copy.xlsx")
```

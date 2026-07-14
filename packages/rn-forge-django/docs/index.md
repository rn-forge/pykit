# rn-forge-django

`rn-forge-django` is the opinionated Django/DRF integration layer built on top of
[`rn-forge-commons`](../rn-forge-commons).

It provides:

- abstract model base classes: status/audit fields, natural-key fixture support, opt-in
  validation-on-save
- a typed, auto-reloading settings facade for the `RN_FORGE_DJANGO` Django setting
- an installable auth app with basic, JWT, and SAML login flows plus DRF authentication/
  permission classes
- DRF base views and mixins: bulk create/delete, CSV/JSON/Excel import-export, audit-field
  population, auth-aware permissions
- Excel-to-fixture generation for Django `loaddata`

Use the guides for common workflows and the API reference for module details.

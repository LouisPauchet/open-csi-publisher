# Branding

The portal's logo and color set are config-driven, not hardcoded in templates/CSS — the
same config-driven-everything approach used for data sources, applied to look-and-feel,
so this codebase can be reused for a non-UNIS deployment without touching HTML or CSS.

## How it works

`src/open_csi_publisher/branding.py::BrandingConfig` defines the fields; `load_branding()`
reads them from a YAML file at `settings.branding_file` (default
`sample_configs/branding.yaml`, resolved against `settings.base_dir` — same pattern as
`settings.sources_file`). If the file doesn't exist, `BrandingConfig()`'s plain, generic
defaults apply instead of erroring — a fresh non-UNIS deployment works out of the box,
just unbranded.

`api/deps.py::get_branding()` is a FastAPI dependency, injected into the two HTML page
routes (`GET /`, `GET /map`) and passed to Jinja2 as `branding`. `templates/base.html`
renders the logo/site name in the header and emits a `<style>` block defining
`--brand-*` CSS custom properties on `:root`; `static/css/site.css` reads those
variables (with its own generic fallback if `--brand-*` is somehow unset) for the
header background, links, buttons, inputs, and the selected-row highlight.

## Fields (`sample_configs/branding.yaml`)

| Field | Meaning |
|---|---|
| `site_name` | Shown in the header and `<title>`. |
| `logo_url` | Full URL to a logo image. Unset ⇒ no logo, text-only header. Not self-hosted — a deployer's logo is expected to already be hosted somewhere (their own site, an object store, etc.); the portal just references it. |
| `color_primary` | Buttons, the site title text, the selected-row highlight tint. |
| `color_secondary` | Body text color. |
| `color_background` | Page background. |
| `color_header_background` | Header bar background. |
| `color_link` / `color_link_hover` | Link color, default and hover. |
| `color_border` | Table/panel/input borders. |
| `font_family` | CSS `font-family` value for body text — a font-stack string, not a webfont fetch (no external font requests are made; if the named font isn't installed locally, it falls through to the rest of the stack, same as any CSS font-family fallback). |
| `heading_font_family` | Same, for `h1`–`h6`. Defaults to `inherit` (no separate heading font). |
| `radius` | Border-radius for buttons/inputs. |

The shipped `sample_configs/branding.yaml` uses UNIS's own public site (www.unis.no)
design tokens — colors, fonts, and the logo URL come straight from
`wp-content/themes/unis/assets/css/vars.css` on unis.no (IBM Plex Sans for body text,
the serif Adamina for headings), so the portal's default look matches the parent site
it's built for.

## Using this for a non-UNIS deployment

Write your own branding YAML and point `BRANDING_FILE` (and `BASE_DIR` if it's not
repo-relative) at it:

```yaml
# my_branding.yaml
site_name: "Acme Weather Network"
logo_url: "https://acme.example/assets/logo.svg"
color_primary: "#1B4965"
color_link: "#1B4965"
```

```sh
export BRANDING_FILE=my_branding.yaml
```

Any field you omit keeps `BrandingConfig`'s generic default rather than falling back to
UNIS's — the two are independent, not layered.

## Manual verification

```sh
curl -s http://127.0.0.1:8000/ | grep -o '<title>[^<]*</title>\|--brand-[a-z-]*: [^;]*;'
```

# Browser and accessibility coverage

No supported-browser matrix was found in project configuration. Existing widget delivery/visual-review documents name Chrome and explicitly exclude Safari and physical mobile testing. CI runs the session VM test on Windows/Linux/macOS; it does not run a browser matrix.

Actual stage-7 controlled runs on Windows:

| Browser | Form/review scenarios | Visible named AX controls | Result |
| --- | --- | --- | --- |
| Chrome 157.0.8103.51 | shop + website at 1280x900, 390x844, 320x568 | 20 desktop; 16 at each mobile width | PASS |
| Edge 157.0.4341.46 | same six scenarios | same counts | PASS |

Both are Chromium-based; this is not cross-engine coverage. The user agents are in the generated reports. Native Tab/Enter exercise form controls and review; Escape closes the mobile service sheet before the widget, returns focus, and preserves form values. Reduced motion disables the typing-dot animation. Checks also cover RTL and horizontal overflow, both themes, and a short 320x568 viewport.

The AX check requires nonempty accessible names for visible buttons, links, textboxes and comboboxes in the initial form. It is not a complete accessibility audit: screen reader speech, contrast, all dynamic AX states and WCAG conformance were not verified. Emulated mobile metrics do not reproduce physical touch, browser chrome, virtual keyboard or device safe areas.

Firefox, Safari/WebKit and physical devices remain untested. A Firefox executable was not found at the usual installation path; its availability elsewhere was not established.

Reproduce from the repository root:

```powershell
node tests/widget_signup_browser.cjs
$env:CHROME_PATH = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
$env:WIDGET_ARTIFACT_DIR = 'artifacts/widget-person3/edge-signup'
node tests/widget_signup_browser.cjs
Remove-Item Env:CHROME_PATH
Remove-Item Env:WIDGET_ARTIFACT_DIR
```

Use a separate PowerShell window for overrides if existing environment values must be retained. No model or production signup is called by these tests.

Independent stage-7 source reviewer found no blocker and did not run browsers. Coverage gaps: AX samples only the shop initial/restored iframe form, not launcher/website/review/error/open modal; dialog checks omit Shift+Tab, full focus-wrap and Space activation; reduced-motion assertion covers typing dots only. These are unverified, not reported as passing.

Stage8 final regression also ran the complete session/loader/offline/refresh suite in both Chrome and Edge with exit0. Committed reports are linked in evidence.md.

Pre-push final runs: Chrome and Edge full quality suites PASS; affected signup suites repeated after persistent-restart fixes PASS, with21 named controls atdesktop and17mobile. Existing-domain and empty-catalog checks, late status race, and session reset despite failed creation/reply were added. Both products still share Chromium. Actual FastAPI/local-mock cross-origin form/review checks passed in Chrome1280/390 with no chat/confirm requests.

# Requests to UTD IT for the CometIQ faculty pilot

Two short requests: one for the identity team (NetID sign-in) and one for the eLearning / Canvas administrators (the Canvas **test** instance). Each can be sent as an email.

In the values below, replace `https://cometiq-pilot.onrender.com` with the pilot's actual URL from Render.

---

## Email 1: Identity and access management (NetID sign-in)

> **Subject:** App registration for the CometIQ faculty pilot (OpenID Connect)
>
> Hello,
>
> JSOM is piloting CometIQ, a curriculum-analysis tool, with a small group of faculty. We would like faculty to sign in with their NetID instead of a separate password. Could you register it as an OpenID Connect web application? Microsoft Entra ID or the Shibboleth OIDC provider both work.
>
> - **Application name:** CometIQ (faculty pilot)
> - **Redirect URI (web):** `https://cometiq-pilot.onrender.com/api/auth/sso/callback`
> - **Flow:** authorization code with PKCE; a client secret is also used.
> - **Scopes:** `openid profile email`
> - **Claims needed:** `email`, `preferred_username` (NetID), `name`.
> - **Roles:** app roles `Faculty`, `Staff` and `Student` in the `roles` claim, or an eduPersonAffiliation-style claim. Assigning only the pilot faculty is fine.
>
> **What we need back:** the issuer URL (for Entra: `https://login.microsoftonline.com/<tenant-id>/v2.0`), the client ID, and the client secret. Please share the secret through your secure channel, not by email.
>
> **Data:** CometIQ stores only the name, email, NetID and the provider's subject ID. Accounts can be exported or deleted on request.
>
> Thank you!

**When it arrives,** set these under the pilot service's **Environment** in Render, then redeploy:

```
SSO_ENABLED=true
SSO_ISSUER=<issuer URL>
SSO_CLIENT_ID=<client id>
SSO_CLIENT_SECRET=<client secret>
SSO_ROLE_CLAIM=roles
SSO_ROLE_MAP=faculty:faculty,staff:advisor,student:student
```

---

## Email 2: eLearning / Canvas administrators (test instance)

> **Subject:** Two developer keys in the Canvas test instance for the CometIQ faculty pilot
>
> Hello,
>
> For the JSOM CometIQ faculty pilot, we would like to connect one course in the **Canvas test instance**. Could you create two developer keys?
>
> **1. API key (read-only):** lets a faculty member import their course's syllabus page and assignments.
> - Admin → Developer Keys → **+ API Key**
> - **Redirect URI:** `https://cometiq-pilot.onrender.com/api/canvas/callback`
> - **Scopes (if you enforce them):** `url:GET|/api/v1/courses`, `url:GET|/api/v1/courses/:id`, `url:GET|/api/v1/courses/:course_id/assignments`
> - We need back: the **client ID** and **key** (secret), through your secure channel.
>
> **2. LTI 1.3 key:** adds a "CometIQ skills" page to the course menu.
> - Admin → Developer Keys → **+ LTI Key** → Method: **Enter URL** → `https://cometiq-pilot.onrender.com/api/lti/config.json`
> - Turn it **On** and install it (by client ID) in the sub-account that holds the test course.
> - We need back: the **client ID** and the **deployment ID**.
>
> **Test setup:** one test course copied from a real JSOM course. It should have a syllabus page and several graded assignments with rubrics, one teacher account (the pilot faculty member) and one student account.
>
> **Data:** CometIQ only reads the course, syllabus page and assignments. Tokens are stored encrypted, and each faculty member can disconnect at any time. Students' grades and submissions are not read.
>
> Thank you!

**When it arrives,** set these and redeploy:

```
CANVAS_BASE_URL=https://<school>.test.instructure.com
CANVAS_CLIENT_ID=<API key client id>
CANVAS_CLIENT_SECRET=<API key secret>
LTI_ENABLED=true
LTI_CLIENT_ID=<LTI key client id>
LTI_DEPLOYMENT_IDS=<deployment id>
LTI_ISSUER=https://canvas.test.instructure.com
LTI_AUTH_URL=https://sso.test.canvaslms.com/api/lti/authorize_redirect
LTI_JWKS_URL=https://sso.test.canvaslms.com/api/lti/security/jwks
```

The last three are the usual addresses for Instructure-hosted **test** environments. Ask the Canvas admins to confirm them; production Canvas uses the defaults without `.test`.

---

## End-to-end test with one real course

Run this once both integrations are configured. Record any problem in the "What happened" column.

| # | Step | Expected | What happened |
|---|---|---|---|
| 1 | Sign in with **NetID** as the pilot faculty member | You land in CometIQ as faculty, and the privacy notice appears once | |
| 2 | CometGap → **Canvas** → Connect Canvas → Authorize | "Connected as <your name>" | |
| 3 | Import the test course | It is matched to its catalog code and semester, the report opens, and the score says **grade-weighted** | |
| 4 | Open the report: check 3 skills against the course you know | The graded work listed for each skill is right, and nothing important is missing | |
| 5 | Change one assignment's rubric in Canvas, then re-import | A new syllabus version is created, and the comparison shows the change | |
| 6 | In Canvas, open the course menu → **CometIQ skills** as the teacher | The page opens inside Canvas, signed in, showing skills, coverage and gaps | |
| 7 | The same as the test student. The pilot admits only faculty, so first set `PILOT_ROLES=admin,faculty,student` and redeploy; set it back afterwards | The skills and "Practiced in" lists appear; no gap or score details are shown | |
| 8 | Review 5 gaps and record one decision | They are saved with your name; the AACSB report lists the decision under "Closing the loop" | |
| 9 | Disconnect Canvas, and as the test student delete the account | The token is revoked, the account is gone, and `deletion-drill` still passes | |

Send the completed table back. Each row that didn't behave as expected becomes a fix in the next release.

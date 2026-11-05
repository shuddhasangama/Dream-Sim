# Initial signup correction — 5 November 2026

The screenshot showed the profile-evolution editor inside initial signup. That exposed saved profile goals, match-window locks, Add detail and Declare a change, despite the user trying to set up an account. The initial picker now lives in signupVision.js and does not render profile history or change/disclosure controls. Existing-account profile evolution remains server protected.

Initial signup shows Vision → Stats → Chemistry → Verification, using one consistent active-step style and a compact grid. The Verified account badge is hidden during setup. Bio remains available later in the profile, rather than occupying the verification step. DigiLocker is shown within Verification rather than the Stats page.

Vision uses the approved Focus Panel: Family / We Two / Travel / Custom in one row and four pillar tiles in two rows. Nothing is selected initially. Family includes all four pillars; We Two includes Intimacy, Cohabitate and Travel; Travel includes Intimacy and Travel. Named plans default to both Emotional and Physical; Cohabitate defaults to Chores, Expenses, Extended family and Pets. Kids and Travel are simple switches with no subchoices. Only Intimacy or Cohabitate opens the single detail panel.

Plan and pillar selection align in both directions. Removing Kids from Family selects We Two. Altering Emotional/Physical or a Cohabitate priority keeps the named plan when its pillar set still fits; other pillar combinations select Custom. Custom starts with Intimacy and no selected details. Saving requires an Intimacy choice, at least one other pillar and a priority when Cohabitate is included. Continue saves and verifies the returned choices before advancing.

The API uses explicit Vision schema version 2 and independently validates the plan against the submitted pillars. It stores real pillars and derived Kids intent. Legacy profiles retain their saved reproductive routes; the new signup neither exposes nor accepts those routes. No new database table is needed.

The sign-in screen no longer renders the OTP-free tester button. After real authentication, an existing dating/relationship account goes to Home instead of being put through initial signup. Development preview may enter the wizard to review the layout with simulated requests; its local code banner is not included in native production behavior. No OTP or vendor request is sent by the screenshot tests.

Scope: this is a local UI correction for the consolidated signup release. Public account creation, fresh-account OTP enrollment, resumed server-side enrollment drafts, new-user DigiLocker eligibility and matching admission still need their agreed E2E integration. Current initial saving uses the protected profile APIs; their lock rules are not bypassed. The change has not been deployed or submitted as another native build.

Review artifact: outputs/signup-redesign-family.png. Tests cover no initial selections; preset switching; no profile change controls; explicit choice before Continue; saving/read-back; Stats validation; Verification as step four; and OTP-only entry.

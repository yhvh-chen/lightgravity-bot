LG-239 run 1 preserved before harness correction.

Outcome: harness assertion bug, no product defect, no Google call.
The admin dialog innerText does not include <input> values (model/base URL), so the
first assertion incorrectly required gemini-3.8-flash and the base URL in innerText.
The dialog visibly reported provider Google native, configured/available, API key
configured, revision 2, and "not verified". Real key setup had succeeded and the
audit log still showed zero Google transport calls.

Correction: assert the model/Base URL input values directly, then rerun without
discarding this snapshot.

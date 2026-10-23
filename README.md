# Royalty Entry

A local Windows program that reads an Excel worksheet and operates License Manager inside the `byumg-remote.byu.edu` Remote Desktop session. It follows the workflow demonstrated in this chat. This is the first implementation: its rules have automated tests, but an end-to-end run against the real workbook and live License Manager still needs verification.

## Launch

Open the **Royalty Entry** desktop shortcut, or `dist\Royalty Entry\Royalty Entry.exe`. This is a standalone Windows desktop application: it does not need a command window or a separate Python installation. Keep the entire `dist\Royalty Entry` folder together because `_internal` contains its bundled runtime. Microsoft Excel must be installed locally for live runs; Excel performs row deletion in a copied workbook so it can adjust formulas and preserve native formatting.

Application data is stored permanently in `%LOCALAPPDATA%\RoyaltyEntry`, independently of the executable. Run reports and the duplicate-payment journal are in its `runs` folder, and calibration is in its `calibration` folder. The first launch imports any journal and calibration bundled from the original source version without overwriting newer application data. Previous reports remain in the source version's `runs` directory.

For source development, **Start.cmd** still launches the Python version. If moving the source to another computer, install Python 3.11 or newer and run **Setup.cmd** once before **Start.cmd**. Both desktop and source versions now share the same per-user data and run lock.

1. Save and close the source Excel workbook. Choose its `.xlsx` or `.xlsm` file.
2. Choose the worksheet, enter the reference, and check the first data row (defaults to 2 for a header in row 1).
3. Keep Remote Desktop connected and visible, with License Manager at its search screen. Keep Search set to **Number**, all required status checkboxes selected, and Song/Publisher filters empty.
4. Click **Test search screen**, then click inside Remote Desktop. The app stays open and waits for that click before checking the screen.
5. Leave **Enable saving payments…** unchecked for the first run. **Start run** performs a preview: it searches licenses, reads balances and transactions, closes the dialogs and writes a CSV report. It does not add payments or delete spreadsheet rows.
6. Review the report against License Manager. Then enable saving and start a live run with the same saved source file, worksheet and reference.

After **Start run**, the app stays visible and displays instructions to click inside Remote Desktop and wait. There is no countdown: processing starts automatically after that click is released. Switching focus with the keyboard alone does not start the run. Keep Royalty Entry on your other monitor so its status and progress bar remain visible. The bar shows preparation activity, then the number and percentage of worksheet rows processed, including duplicate and review rows. It also identifies final workbook/report preparation; a stopped run retains its partial progress.

During a run, leave the mouse and keyboard alone. **Hold Esc** to stop, or switch to the program and press **Stop**. Stop also cancels a run that is still waiting for your Remote Desktop click. Switching focus away from Remote Desktop during processing causes the next screen check to fail and stop. The program does not take over your computer immediately on launch.

## Rules

- Publisher is in H; license is in I. Text license numbers retain leading zeroes. Numeric license numbers with a zero-padding number format are padded accordingly.
- Each license/publisher pair is evaluated once, including duplicates that are not adjacent. A different publisher is processed separately. Publisher matching ignores case and repeated whitespace, but never uses a fuzzy match.
- Provisional Balance **below −0.01**: remove that pair's rows from the results tab.
- Balance **−0.01 or greater**: inspect Financials. No Transfer: remove that pair's rows from the results tab.
- Exactly one Transfer: add **PAYMENT OF ROYALTIES**, with amount **Transfer − 0.01**, and the entered reference. Preserve the form's default Date and Royalty Period, as demonstrated.
- Select the type in **Transaction Types**, click its OK, then enter the amount/reference. Save with the three OK buttons: transaction, Financial Transactions, license Properties.
- Verify the updated balance in both Financial Transactions and Details before considering the pair complete.
- Single-value monetary fields use enlarged grayscale and contrast readings to handle short ClearType numbers. At least two readings must agree, the displayed two-decimal format must be present, and conflicting signs or digits stop processing. Balances are still checked in two separate screen captures. **Read displayed balance** checks an already open Details tab without adding entries or editing the workbook.
- A missing exact license/publisher match or invalid input row stays in the output for review. An unreadable or unexpected screen stops the run; the program does not guess a financial value or assume that OCR silence means no Transfer.
- General-tab identity edits use repeated border-free, enlarged readings. License digits are compared exactly after joining OCR digit groups. Publisher names require a unique leading result with at least three identical readings across seven OCR passes after removing the displayed `PUB` code. That result must exactly match the workbook name. Ambiguous readings stop the run; no letters are substituted for license digits and publisher names are not fuzzily matched.
- Transfer amounts are reread from the matching row's cell with repeated agreement, including selected blue rows. The amount crop excludes the grid separator so it cannot become an extra digit. Historical non-Transfer amounts do not affect the decision.
- The transaction-type chooser includes the full first letter and requires two exact reads of PAYMENT OF ROYALTIES at the same row position. The returned entry-type field also includes the complete label before verification.
- Amounts are entered directly with keyboard input and checked against two separate screen reads. They do not depend on copying from the legacy numeric edit. Other pasted fields that cannot copy back must match two exact displayed readings; clipboard marker text is never accepted as verification.
- Duplicate rows remain for paid pairs. All rows of rejected duplicate pairs are removed from the results tab. Live runs add a new filtered tab to the selected workbook; the source tab is preserved. If any publisher receives payment, all rows for that license are retained.

## Two monitors and calibration

Coordinates are relative to the Remote Desktop window; it can be on either monitor, including a monitor with negative desktop coordinates. Keep the entire Remote Desktop window on screen. Local Excel does not need to be visible while processing because the program reads the selected saved file directly.

The **1907 × 1032** profile is now a logical reference image, not a required monitor or window size. At startup, the app enables Remote Desktop’s **Smart sizing** option, which fits the full remote session into your current window. It does not enlarge the window or require a larger monitor.

Before reading or searching licenses, startup identifies the **Mechanical Royalty Module** title bar inside the remote session and invokes its Maximize command. An already maximized module stays maximized. The app checks the module title again, then locates License Manager again before starting the sequence. This maximizes the remote module rather than the local Remote Desktop window. At 85% display scale or larger, startup reads directly from the visible screen and does not need clipboard images. Smaller views use full-resolution clipboard captures, allowing the clipboard to settle first and retrying up to three times if an image does not arrive. Startup no longer requests a separate active-window clipboard screenshot.

On each capture, graphical matching locates License Manager’s toolbar and measures its displayed scale and offset. Clicks are mapped back with that measured transform and the actual Remote Desktop window position. When the displayed view is reduced below 85%, the app uses Remote Desktop’s full-resolution clipboard snapshot for text recognition, with a separate transform for reading. This requires clipboard image redirection. Each snapshot must be fresh; stale clipboard images are rejected. The app uses the clipboard during processing, so its previous contents are replaced. Moving to another monitor or resizing the view does not require multiplying the whole window’s dimensions by an assumed ratio. The app checks that the target control is within the visible view before clicking it. An uncertain or ambiguous toolbar match stops processing.

Keep License Manager’s toolbar visible inside the remote session. Smart sizing may also be enabled manually from the Remote Desktop title-bar menu. If the remote dialogs themselves are rearranged relative to the original layout, use **Screen calibration…**; calibration is captured in the same logical reference space. Reduced on-screen text is read from the native remote snapshot rather than enlarged from the tiny displayed text. Unreadable native text or unavailable image redirection stops the run. Review a preview at the intended window size before enabling payments.

The calibration editor displays a static capture. Open each screen yourself, click **Capture Remote Desktop in 5 seconds**, and focus Remote Desktop. Then pick each field in the editor and draw its text rectangle or click its button center on the picture. These selections do not click the remote app. The screens are:

1. License Manager search results (`manager_`, `search_`, `result_`).
2. Properties, General tab (`properties_title`, `general_`, `details_tab`, `properties_ok`).
3. Properties, Details tab (`details_label`, `details_balance`, `financials_button`).
4. Financial Transactions (`financials_`).
5. Financial Transaction entry (`entry_`, `type_button`).
6. Transaction Types (`chooser_`).

For each pair of table columns, draw boxes with **exactly the same top and bottom** and include only data rows, without headings or the scrollbar. The `details_label` box should contain only `Provisional Balance:`. Title boxes must contain the title text, excluding icons and close buttons. The `entry_type` and `general_publisher` boxes should exclude their icons. Give amount boxes enough space to include the minus sign and every digit. Merely changing the local Remote Desktop window size does not require recalibrating these logical fields.

Do not move, resize or reorder remote windows after calibration. If you opened an entry for calibration, cancel it yourself when done. Test again, then preview. OCR can misread small text: review the first preview against the real screens before enabling live entries. No full live run has been validated yet.

## Output and restart behavior

Each run creates a dated folder inside `%LOCALAPPDATA%\RoyaltyEntry\runs` containing:

- A recovery workbook copy. Live runs also save a uniquely named `Royalty YYYYMMDD-HHMMSS` tab inside the selected workbook.
- `report.csv`, showing original row numbers, decisions, payment amounts, and any stop/error.

Live runs copy the selected source worksheet to a new tab and delete rejected rows only from that new tab. Save and close the workbook before starting: write access is checked before payments begin. Native Excel preserves formatting and adjusts formulas during deletion. Macros and workbook events are disabled and external-link updates are suppressed. Preview runs do not add tabs.

`%LOCALAPPDATA%\RoyaltyEntry\runs\journal.sqlite3` is shared by all copies of the app running under this Windows account. It records completed pairs by license, publisher and normalized reference, even when the program is restarted or a different workbook is selected. A matching completed entry is not added again. Use the same reference for a resumed run. Keep this journal; deleting it removes this protection. Other Windows accounts or computers do not share it automatically.

Immediately before saving a payment, its journal state becomes `pending`. If the connection drops or a save is interrupted, the program will stop rather than add it again. Use **Interrupted entries…** only after closing any unfinished dialogs and reopening Financials to check the actual saved Type, amount and reference. Mark it verified saved, or verified not saved to permit a retry. The program cannot make a database transaction atomic across Remote Desktop and the local journal.

If creating the final filtered workbook fails after some payments were saved, those payments remain saved. The source tab stays unchanged; use the recovery workbook if the results tab cannot be saved. Preserve the journal and report, fix the Excel/output problem and rerun with the same source and reference; recorded entries will be skipped and recorded removal decisions reapplied.

## Development and validation

Run `.venv\Scripts\python.exe -m pytest -q` after installing `pytest` in the environment. Tests cover decimal arithmetic, threshold boundaries, duplicate pairs, publisher distinctions, previews, missing matches, restart blocking, row alignment and workbook input handling. Screen input is replaced by a fake driver in these tests; passing them does not establish that live screen calibration is correct.

OCR uses the local [Windows OCR API](https://learn.microsoft.com/en-us/uwp/api/windows.media.ocr.ocrengine.recognizeasync) through [PyWinRT](https://pywinrt.readthedocs.io/). English OCR must be available in Windows. Screenshots and worksheet values are not sent to an online OCR service. Financial values are calculated with Python `Decimal`.

To rebuild the desktop app, install `pyinstaller>=6.16,<7` in `.venv` and run **Build.cmd**. `desktop-app.spec` includes the local OCR bindings, Excel integration, Tk GUI and app icon. Rebuilding the distribution does not modify the permanent application data directory.

Publisher identifiers: column G contains PUB/PB numbers, column H is the display name, and column I is the license number. When column G is populated, search matching, opened-license verification and duplicate detection use the publisher number. Existing name-keyed payment history remains honored during upgrades. Older sheets without column G retain name-based matching.

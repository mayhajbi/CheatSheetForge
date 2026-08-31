# בדיקת היתכנות RTL (PoC) — מסקנות

לפי החלטה 11 בפרק 10 של ה-PRD, תמיכת ה-RTL נבדקה לפני השקעה בשאר תכונות הייצוא.

## מה נבדק בפועל

`backend/export/docx_builder.py` בונה docx מ-`fixtures/sample_merged.json`, ובדיקה
אוטומטית (`backend/export/tests/test_export.py::test_hebrew_paragraphs_are_rtl_and_code_lines_are_ltr`)
מוודאת ברמת ה-XML של הקובץ שנוצר:

- כל פסקת עברית מקבלת `<w:bidi w:val="1"/>` ויישור לימין.
- כל שורת נוסחה/קוד באנגלית יושבת בפסקה נפרדת עם `<w:bidi w:val="0"/>`,
  ולא מעורבת בתוך שורת עברית (הכלל מפרק 05).

זו בדיקה מבנית על הקובץ שנוצר, ולא בדיקה ויזואלית ב-Word — כדאי לפתוח פעם אחת
קובץ פלט אמיתי ב-Word לפני ההצגה, כדי לאמת גם את המראה.

## מה טרם נבדק

מסלול ה-PDF (`soffice --headless --convert-to pdf`) לא הורץ בסביבת הפיתוח
המקומית (LibreOffice לא מותקן שם, והבדיקה מדלגת אוטומטית). ב-Railway הוא מותקן
דרך `nixpacks.toml`. אם יתגלה שיבוש RTL בהמרה — המסלול החלופי הוא WeasyPrint,
ראו `build_pdf_via_weasyprint()` ב-`backend/export/pdf_builder.py`.

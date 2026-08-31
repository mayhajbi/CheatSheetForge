import { useState } from "react";
import { exportBank, deleteSession } from "../api.js";

// שמירה מקומית: File System Access API נתמך רק בדפדפני Chromium (Chrome/Edge).
// בדפדפנים אחרים נופלים אוטומטית להורדת קובץ רגילה (<a download>) -- ראו
// נקודה 20 בפרק 10 של ה-PRD (נדרשת החלטה טכנית קטנה; כאן ממומש ה-fallback
// כברירת מחדל הבטוחה יותר לדמו).
async function saveFile(blob, filename) {
  if (window.showSaveFilePicker) {
    try {
      const handle = await window.showSaveFilePicker({ suggestedName: filename });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      return;
    } catch (err) {
      if (err.name === "AbortError") return; // המשתמש ביטל את הדיאלוג
      // נופלים ל-fallback הרגיל אם ה-API נכשל מסיבה אחרת
    }
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export default function ExportScreen({ sessionId, maxPages, onStartOver }) {
  const [format, setFormat] = useState("docx");
  const [fontName, setFontName] = useState("Arial");
  const [fontSize, setFontSize] = useState(11);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);

  async function handleExport() {
    setLoading(true);
    setError(null);
    try {
      const blob = await exportBank(sessionId, format, fontName, fontSize);
      await saveFile(blob, `cheatsheet.${format}`);
      setDone(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleFinish() {
    // מחיקה מלאה בצד השרת בסיום הסשן -- ראו פרק 07 (החלטה סופית, ללא אחסון קבוע)
    await deleteSession(sessionId);
    onStartOver();
  }

  return (
    <section className="card">
      <h2>שלב 3: ייצוא דף הנוסחאות</h2>
      <p className="hint">מגבלת עמודים שהוגדרה: {maxPages}. פורמט A4, שוליים צרים.</p>

      <div className="form">
        <label>
          פורמט
          <select value={format} onChange={(e) => setFormat(e.target.value)}>
            <option value="docx">Word (docx)</option>
            <option value="pdf">PDF</option>
          </select>
        </label>

        <label>
          גופן
          <input value={fontName} onChange={(e) => setFontName(e.target.value)} />
        </label>

        <label>
          גודל כתב (pt)
          <input
            type="number"
            min={8}
            max={16}
            value={fontSize}
            onChange={(e) => setFontSize(Number(e.target.value))}
          />
        </label>

        {error && <div className="error">{error}</div>}

        <button onClick={handleExport} disabled={loading}>
          {loading ? "מייצא..." : "הורד קובץ"}
        </button>
      </div>

      {done && (
        <div className="notice">
          הקובץ ירד בהצלחה. כל הנתונים נמחקים מהשרת בסיום -- לחצו "סיום"
          כדי לנקות את ה-session ולהתחיל פרויקט חדש (או להמשיך פרויקט קיים
          על ידי העלאה מחדש של הקובץ שנשמר).
          <button onClick={handleFinish}>סיום</button>
        </div>
      )}
    </section>
  );
}

import { useState } from "react";
import { uploadFiles } from "../api.js";

const MAX_FILES = 15;
const MAX_TOTAL_MB = 5;

export default function UploadScreen({ onUploaded }) {
  const [course, setCourse] = useState("מערכות הפעלה");
  const [examFiles, setExamFiles] = useState([]);
  const [syllabusFile, setSyllabusFile] = useState(null);
  const [maxPages, setMaxPages] = useState(4);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const totalMb = examFiles.reduce((sum, f) => sum + f.size, 0) / (1024 * 1024);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);

    if (examFiles.length === 0) {
      setError("יש להעלות לפחות קובץ מבחן/תרגיל אחד.");
      return;
    }
    if (!syllabusFile) {
      setError("יש להעלות קובץ סילבוס.");
      return;
    }
    if (examFiles.length > MAX_FILES) {
      setError(`עד ${MAX_FILES} קבצים בהעלאה בודדת. ניתן להמשיך מאוחר יותר עם אצווה נוספת.`);
      return;
    }
    if (totalMb > MAX_TOTAL_MB) {
      setError(`חריגה ממגבלת הגודל הכוללת (${MAX_TOTAL_MB}MB).`);
      return;
    }

    setLoading(true);
    try {
      const res = await uploadFiles({ course, maxPages, examFiles, syllabusFile });
      setResult(res);
      onUploaded(res.session_id, maxPages);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="card">
      <h2>שלב 1: העלאת קבצים</h2>

      <div className="notice">
        <strong>המלצה לאיכות קלט:</strong> יש להעלות קבצים באיכות סריקה/הדפסה
        גבוהה, כדי לא לפגוע בדיוק המידע המחולץ.
      </div>
      <div className="notice">
        מגבלת העלאה בודדת: עד {MAX_FILES} קבצים / עד {MAX_TOTAL_MB}MB בסך הכול.
        אפשר תמיד לחזור מאוחר יותר ולהוסיף אצווה נוספת על גבי התוצאה השמורה.
      </div>

      <form onSubmit={handleSubmit} className="form">
        <label>
          קורס
          <input value={course} onChange={(e) => setCourse(e.target.value)} required />
        </label>

        <label>
          קובצי מבחנים/תרגילים פתורים (PDF, כולל תשובות)
          <input
            type="file"
            accept="application/pdf"
            multiple
            onChange={(e) => setExamFiles(Array.from(e.target.files))}
            required
          />
          {examFiles.length > 0 && (
            <span className="hint">
              {examFiles.length} קבצים נבחרו, {totalMb.toFixed(1)}MB
            </span>
          )}
        </label>

        <label>
          קובץ סילבוס (PDF)
          <input
            type="file"
            accept="application/pdf"
            onChange={(e) => setSyllabusFile(e.target.files[0])}
            required
          />
        </label>

        <label>
          כמות דפים מקסימלית לדף הנוסחאות הסופי
          <input
            type="number"
            min={1}
            max={20}
            value={maxPages}
            onChange={(e) => setMaxPages(Number(e.target.value))}
            required
          />
        </label>

        {error && <div className="error">{error}</div>}

        <button type="submit" disabled={loading}>
          {loading ? "מעבד..." : "העלה וסווג"}
        </button>
      </form>

      {result && result.failed_files.length > 0 && (
        <div className="warning">
          הקבצים הבאים נכשלו בחילוץ ולא נכללו: {result.failed_files.join(", ")}
        </div>
      )}
    </section>
  );
}

import { useEffect, useState } from "react";
import { mergeSession, removeItems } from "../api.js";

const TYPE_LABELS = { closed: "שאלה סגורה", open_calc: "שאלה פתוחה", code: "מימוש קוד" };

export default function PreviewScreen({ sessionId, onMerged, onReadyToExport }) {
  const [bank, setBank] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [removedSet, setRemovedSet] = useState(new Set());

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    mergeSession(sessionId)
      .then((merged) => {
        if (!cancelled) {
          setBank(merged);
          onMerged(merged);
        }
      })
      .catch((err) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  function toggleRemoved(index) {
    setRemovedSet((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }

  async function handleConfirmRemovals() {
    if (removedSet.size === 0) {
      onReadyToExport();
      return;
    }
    try {
      const updated = await removeItems(sessionId, Array.from(removedSet));
      setBank(updated);
      onMerged(updated);
      setRemovedSet(new Set());
    } catch (err) {
      setError(err.message);
      return;
    }
    onReadyToExport();
  }

  if (loading) return <section className="card">מריץ מנוע איחוד כפילויות...</section>;
  if (error) return <section className="card error">{error}</section>;
  if (!bank) return null;

  return (
    <section className="card">
      <h2>שלב 2: תצוגה מקדימה של הבנק המרוכז</h2>
      <p className="hint">
        {bank.items.length} פריטים בבנק, קורס: {bank.course}. סמנו פריטים
        להסרה (לדוגמה נושא שאינו בחומר הסמסטר) — עריכת תוכן פריטים אינה
        נתמכת ב-MVP הנוכחי.
      </p>

      <ul className="item-list">
        {bank.items.map((item, index) => (
          <li key={index} className={removedSet.has(index) ? "removed" : ""}>
            <label>
              <input
                type="checkbox"
                checked={removedSet.has(index)}
                onChange={() => toggleRemoved(index)}
              />
              <span className="badge">{TYPE_LABELS[item.type]}</span>
              <span className="topic">{item.topic}</span>
              <span className="preview-text">
                {item.type === "closed" && item.question_text}
                {item.type === "open_calc" && item.representative.question_text}
                {item.type === "code" && "הפניה לשאלת קוד (ללא שכפול טקסט)"}
              </span>
            </label>
          </li>
        ))}
      </ul>

      <button onClick={handleConfirmRemovals}>המשך לייצוא</button>
    </section>
  );
}

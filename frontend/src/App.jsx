import { useState } from "react";
import UploadScreen from "./components/UploadScreen.jsx";
import PreviewScreen from "./components/PreviewScreen.jsx";
import ExportScreen from "./components/ExportScreen.jsx";

// שלושה מסכים לפי תרחיש השימוש המרכזי בפרק 02 של ה-PRD:
// העלאה -> תצוגה מקדימה/סינון -> ייצוא.
const STEPS = { UPLOAD: "upload", PREVIEW: "preview", EXPORT: "export" };

export default function App() {
  const [step, setStep] = useState(STEPS.UPLOAD);
  const [sessionId, setSessionId] = useState(null);
  const [maxPages, setMaxPages] = useState(4);
  const [bank, setBank] = useState(null);

  function handleUploaded(newSessionId, chosenMaxPages) {
    setSessionId(newSessionId);
    setMaxPages(chosenMaxPages);
    setStep(STEPS.PREVIEW);
  }

  function handleMerged(mergedBank) {
    setBank(mergedBank);
  }

  function handleReadyToExport() {
    setStep(STEPS.EXPORT);
  }

  function handleStartOver() {
    setSessionId(null);
    setBank(null);
    setStep(STEPS.UPLOAD);
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>CheatSheetForge</h1>
        <p className="subtitle">מחולל דף נוסחאות ממבחני עבר</p>
        <ol className="stepper">
          <li className={step === STEPS.UPLOAD ? "active" : ""}>1. העלאה</li>
          <li className={step === STEPS.PREVIEW ? "active" : ""}>2. תצוגה מקדימה</li>
          <li className={step === STEPS.EXPORT ? "active" : ""}>3. ייצוא</li>
        </ol>
      </header>

      <main>
        {step === STEPS.UPLOAD && <UploadScreen onUploaded={handleUploaded} />}
        {step === STEPS.PREVIEW && sessionId && (
          <PreviewScreen
            sessionId={sessionId}
            onMerged={handleMerged}
            onReadyToExport={handleReadyToExport}
          />
        )}
        {step === STEPS.EXPORT && sessionId && (
          <ExportScreen sessionId={sessionId} maxPages={maxPages} onStartOver={handleStartOver} />
        )}
      </main>
    </div>
  );
}

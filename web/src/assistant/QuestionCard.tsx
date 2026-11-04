/**
 * The questions of one `ask_user` call: radio buttons, checkboxes or a text field, with an
 * optional free-text answer. The run has ended when this shows; sending starts the next one.
 */

import { useId, useState, type FormEvent } from "react";

import type { AssistantAnswer, AssistantQuestion, AssistantQuestionSet } from "../contracts/assistant";
import { ChatMarkdown } from "./ChatMarkdown";

interface Draft {
  values: string[];
  other: string;
  otherOn: boolean;
}

const EMPTY: Draft = { values: [], other: "", otherOn: false };

/** The answer as the backend wants it; `null` when a required question has none yet. */
export function answerOf(question: AssistantQuestion, draft: Draft): AssistantAnswer | null {
  const other = question.kind === "text" || draft.otherOn ? draft.other.trim() : "";
  if (draft.values.length === 0 && other === "" && question.optional !== true) {
    return null;
  }
  return { questionId: question.id, values: draft.values, other: other === "" ? null : other };
}

interface FieldProps {
  question: AssistantQuestion;
  draft: Draft;
  disabled: boolean;
  onChange: (next: Draft) => void;
}

function Field({ question, draft, disabled, onChange }: FieldProps) {
  const name = useId();
  const textId = useId();
  if (question.kind === "text") {
    return (
      <>
        <div id={textId} className="assistant-question__prompt">
          <ChatMarkdown text={question.prompt} />
        </div>
        <textarea
          className="assistant-question__text"
          rows={2}
          aria-labelledby={textId}
          value={draft.other}
          disabled={disabled}
          onChange={(event) => onChange({ ...draft, other: event.target.value })}
        />
      </>
    );
  }
  const single = question.kind === "single";
  const toggle = (value: string, on: boolean): void => {
    if (single) {
      onChange({ ...draft, values: [value], otherOn: false });
    } else {
      onChange({ ...draft, values: on ? [...draft.values, value] : draft.values.filter((v) => v !== value) });
    }
  };
  return (
    <fieldset className="assistant-question__field" disabled={disabled}>
      <legend className="assistant-question__prompt">
        <ChatMarkdown text={question.prompt} />
      </legend>
      {(question.options ?? []).map((option) => (
        <label key={option.value} className="assistant-question__option">
          <input
            type={single ? "radio" : "checkbox"}
            name={name}
            checked={draft.values.includes(option.value)}
            onChange={(event) => toggle(option.value, event.target.checked)}
          />
          <span>
            <span className="assistant-question__label">{option.label}</span>
            {option.description === undefined ? null : (
              <span className="assistant-question__hint">
                <ChatMarkdown text={option.description} />
              </span>
            )}
          </span>
        </label>
      ))}
      {question.allowOther === true ? (
        <label className="assistant-question__option">
          <input
            type={single ? "radio" : "checkbox"}
            name={name}
            checked={draft.otherOn}
            onChange={(event) =>
              onChange({ ...draft, otherOn: event.target.checked, values: single ? [] : draft.values })
            }
          />
          <span className="assistant-question__label">Other</span>
        </label>
      ) : null}
      {draft.otherOn ? (
        <input
          type="text"
          className="assistant-question__other"
          aria-label={`Other answer: ${question.prompt}`}
          value={draft.other}
          onChange={(event) => onChange({ ...draft, other: event.target.value })}
        />
      ) : null}
    </fieldset>
  );
}

export interface QuestionCardProps {
  question: AssistantQuestionSet;
  /** Answered, or passed over by a typed message: the card only records what was asked. */
  answered: boolean;
  busy: boolean;
  onAnswer: (answers: AssistantAnswer[]) => void;
}

export function QuestionCard({ question, answered, busy, onAnswer }: QuestionCardProps) {
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const answers = question.questions.map((item) => answerOf(item, drafts[item.id] ?? EMPTY));
  const complete = answers.every((answer) => answer !== null);
  const submit = (event: FormEvent): void => {
    event.preventDefault();
    if (complete) {
      onAnswer(answers.filter((answer) => answer !== null));
    }
  };
  return (
    <form className="assistant-question" data-testid="question-card" data-answered={answered} onSubmit={submit}>
      {question.title === undefined ? null : <h3 className="assistant-question__title">{question.title}</h3>}
      {question.questions.map((item) => (
        <Field
          key={item.id}
          question={item}
          draft={drafts[item.id] ?? EMPTY}
          disabled={answered}
          onChange={(next) => setDrafts((current) => ({ ...current, [item.id]: next }))}
        />
      ))}
      {answered ? null : (
        <button
          type="submit"
          className="assistant-button assistant-button--primary"
          disabled={!complete || busy}
          data-testid="question-send"
        >
          Send answers
        </button>
      )}
    </form>
  );
}

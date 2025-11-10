'use client';

/**
 * QuizPane Component
 *
 * Interactive quiz interface with submission, grading, and results (PR-089).
 * Supports: multiple choice, multi-select, real-time validation, attempt tracking.
 */

import { useState } from 'react';
import { useRouter } from 'next/navigation';

interface QuizPaneProps {
  quizId: string;
  courseId: string;
}

interface Question {
  id: string;
  question_text: string;
  options: string[];
  order_index: number;
  points: number;
}

export default function QuizPane({ quizId, courseId }: QuizPaneProps) {
  const [questions, setQuestions] = useState<Question[]>([]);
  const [answers, setAnswers] = useState<Record<string, number[]>>({});
  const [submitted, setSubmitted] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [submitting, setSubmitting] = useState(false);
  const router = useRouter();

  const handleAnswer = (questionId: string, optionIndex: number) => {
    setAnswers((prev) => {
      const current = prev[questionId] || [];
      const newAnswers = current.includes(optionIndex)
        ? current.filter((i) => i !== optionIndex)
        : [...current, optionIndex];
      return { ...prev, [questionId]: newAnswers };
    });
  };

  const handleSubmit = async () => {
    try {
      setSubmitting(true);
      const response = await fetch('/api/v1/education/attempts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          course_id: courseId,
          quiz_id: quizId,
          answers,
        }),
      });

      if (!response.ok) throw new Error('Submission failed');

      const data = await response.json();
      setResult(data);
      setSubmitted(true);
    } catch (error) {
      console.error('Quiz submission failed:', error);
      alert('Failed to submit quiz. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  if (submitted && result) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-8">
        <div className={`text-center p-8 rounded-lg ${result.passed ? 'bg-green-50 dark:bg-green-900/20' : 'bg-red-50 dark:bg-red-900/20'}`}>
          <div className="text-6xl mb-4">{result.passed ? '✅' : '❌'}</div>
          <h2 className="text-2xl font-bold mb-2">
            {result.passed ? 'Congratulations!' : 'Keep Trying!'}
          </h2>
          <p className="text-xl mb-4">Score: {result.score.toFixed(1)}%</p>
          {result.passed ? (
            <p className="text-green-700 dark:text-green-300 mb-6">
              You've passed this quiz! {result.grading_details?.reward_issued && '🎁 Reward unlocked!'}
            </p>
          ) : (
            <p className="text-red-700 dark:text-red-300 mb-6">
              You need {result.grading_details?.passing_score}% to pass. Review the lesson and try again.
            </p>
          )}
          <button
            onClick={() => router.push(`/education/course/${courseId}`)}
            className="px-6 py-2 bg-primary-500 hover:bg-primary-600 text-white rounded-lg"
          >
            Back to Course
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">Quiz</h1>

      {questions.map((q, idx) => (
        <div key={q.id} className="mb-8 p-6 bg-white dark:bg-gray-800 rounded-lg border">
          <h3 className="font-medium text-lg mb-4">
            {idx + 1}. {q.question_text}
          </h3>
          <div className="space-y-2">
            {q.options.map((option, optIdx) => (
              <label key={optIdx} className="flex items-center gap-3 p-3 rounded hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={(answers[q.id] || []).includes(optIdx)}
                  onChange={() => handleAnswer(q.id, optIdx)}
                  className="w-5 h-5"
                />
                <span>{option}</span>
              </label>
            ))}
          </div>
        </div>
      ))}

      <button
        onClick={handleSubmit}
        disabled={submitting || Object.keys(answers).length === 0}
        className="w-full px-6 py-3 bg-primary-500 hover:bg-primary-600 disabled:bg-gray-300 text-white rounded-lg font-medium"
      >
        {submitting ? 'Submitting...' : 'Submit Quiz'}
      </button>
    </div>
  );
}

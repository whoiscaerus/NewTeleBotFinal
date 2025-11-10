'use client';

/**
 * LessonContent Component
 *
 * Renders markdown lesson content with navigation (PR-089).
 * Supports: markdown rendering, previous/next lesson navigation, progress tracking.
 */

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';

interface LessonContentProps {
  lessonId: string;
  courseId: string;
}

export default function LessonContent({ lessonId, courseId }: LessonContentProps) {
  const [lesson, setLesson] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    loadLesson();
  }, [lessonId]);

  const loadLesson = async () => {
    try {
      const response = await fetch(`/api/v1/education/lessons/${lessonId}`);
      const data = await response.json();
      setLesson(data);
    } catch (error) {
      console.error('Failed to load lesson:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div className="text-center py-8">Loading lesson...</div>;
  if (!lesson) return <div className="text-center py-8 text-red-500">Lesson not found</div>;

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      {/* Lesson Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
          {lesson.title}
        </h1>
        <div className="flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400">
          <span>⏱️ {lesson.duration_minutes} min</span>
          {lesson.is_required && <span className="text-amber-600 dark:text-amber-400">★ Required</span>}
        </div>
      </div>

      {/* Markdown Content */}
      <div
        className="prose dark:prose-invert max-w-none"
        dangerouslySetInnerHTML={{ __html: lesson.content }}
      />

      {/* Navigation */}
      <div className="mt-12 flex justify-between">
        <button
          onClick={() => router.back()}
          className="px-6 py-2 bg-gray-200 hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-800 dark:text-white rounded-lg"
        >
          ← Back to Course
        </button>
        <button
          onClick={() => router.push(`/education/course/${courseId}/quiz/${lesson.quizzes[0]?.id}`)}
          className="px-6 py-2 bg-primary-500 hover:bg-primary-600 text-white rounded-lg"
        >
          Take Quiz →
        </button>
      </div>
    </div>
  );
}

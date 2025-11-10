'use client';

import { useEffect, useState } from 'react';
import CourseCard from '@/components/CourseCard';
import Header from '@/components/Header';
import Footer from '@/components/Footer';

/**
 * Education Hub Page
 *
 * Displays micro-courses (RSI, risk management) with quizzes and rewards.
 * Integrated with Mini App & web (PR-089).
 *
 * Features:
 * - Course listing with difficulty, duration, rewards
 * - Progress tracking (completed lessons/courses)
 * - Filter by difficulty level
 * - Responsive grid layout
 */

interface Course {
  id: string;
  title: string;
  description: string;
  duration_minutes: number;
  difficulty_level: number; // 1=beginner, 2=intermediate, 3=advanced
  reward_percent: number | null;
  reward_expires_days: number | null;
  thumbnail_url: string | null;
  order_index: number;
}

export default function EducationPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [difficultyFilter, setDifficultyFilter] = useState<number | null>(null);

  useEffect(() => {
    loadCourses();
  }, []);

  const loadCourses = async () => {
    try {
      setLoading(true);
      setError(null);

      // Fetch courses from API
      const response = await fetch('/api/v1/education/courses', {
        headers: {
          'Content-Type': 'application/json',
          // JWT token will be added by middleware
        },
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      setCourses(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load courses';
      setError(message);
      console.error('Failed to load courses:', err);
    } finally {
      setLoading(false);
    }
  };

  const filteredCourses =
    difficultyFilter === null
      ? courses
      : courses.filter((c) => c.difficulty_level === difficultyFilter);

  const difficultyLabels: Record<number, string> = {
    1: 'Beginner',
    2: 'Intermediate',
    3: 'Advanced',
  };

  return (
    <>
      <Header />
      <main className="min-h-screen bg-gray-50 dark:bg-gray-900 py-8">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          {/* Page Header */}
          <div className="text-center mb-12">
            <h1 className="text-4xl font-bold text-gray-900 dark:text-white mb-4">
              📚 Education Hub
            </h1>
            <p className="text-lg text-gray-600 dark:text-gray-400 max-w-2xl mx-auto">
              Master trading fundamentals with interactive courses, quizzes, and
              rewards. Learn RSI, risk management, position sizing, and more.
            </p>
          </div>

          {/* Difficulty Filter */}
          <div className="flex justify-center gap-3 mb-8 flex-wrap">
            <button
              onClick={() => setDifficultyFilter(null)}
              className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                difficultyFilter === null
                  ? 'bg-primary-500 text-white'
                  : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
              }`}
            >
              All Levels
            </button>
            {[1, 2, 3].map((level) => (
              <button
                key={level}
                onClick={() => setDifficultyFilter(level)}
                className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                  difficultyFilter === level
                    ? 'bg-primary-500 text-white'
                    : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                }`}
              >
                {difficultyLabels[level]}
              </button>
            ))}
          </div>

          {/* Loading State */}
          {loading && (
            <div className="text-center py-16">
              <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-primary-500"></div>
              <p className="mt-4 text-gray-600 dark:text-gray-400">
                Loading courses...
              </p>
            </div>
          )}

          {/* Error State */}
          {error && (
            <div className="max-w-md mx-auto bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6 text-center">
              <p className="text-red-600 dark:text-red-400 font-medium mb-2">
                ⚠️ Error Loading Courses
              </p>
              <p className="text-red-500 dark:text-red-300 text-sm mb-4">
                {error}
              </p>
              <button
                onClick={loadCourses}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors"
              >
                Retry
              </button>
            </div>
          )}

          {/* Empty State */}
          {!loading && !error && filteredCourses.length === 0 && (
            <div className="text-center py-16">
              <p className="text-gray-500 dark:text-gray-400 text-lg">
                {difficultyFilter !== null
                  ? `No courses found for ${difficultyLabels[difficultyFilter]} level.`
                  : 'No courses available yet. Check back soon!'}
              </p>
            </div>
          )}

          {/* Course Grid */}
          {!loading && !error && filteredCourses.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {filteredCourses.map((course) => (
                <CourseCard key={course.id} course={course} />
              ))}
            </div>
          )}

          {/* Stats Summary */}
          {!loading && !error && courses.length > 0 && (
            <div className="mt-12 text-center text-gray-600 dark:text-gray-400">
              <p>
                {courses.length} course{courses.length === 1 ? '' : 's'} available
                {difficultyFilter !== null &&
                  ` • ${filteredCourses.length} ${difficultyLabels[difficultyFilter]}`}
              </p>
            </div>
          )}
        </div>
      </main>
      <Footer />
    </>
  );
}

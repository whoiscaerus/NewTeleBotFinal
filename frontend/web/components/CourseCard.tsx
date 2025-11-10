'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';

/**
 * CourseCard Component
 *
 * Displays course metadata with progress, difficulty badge, reward info, and CTA.
 * Used in Education Hub grid layout (PR-089).
 */

interface CourseCardProps {
  course: {
    id: string;
    title: string;
    description: string;
    duration_minutes: number;
    difficulty_level: number; // 1=beginner, 2=intermediate, 3=advanced
    reward_percent: number | null;
    reward_expires_days: number | null;
    thumbnail_url: string | null;
  };
}

export default function CourseCard({ course }: CourseCardProps) {
  const router = useRouter();

  const difficultyConfig = {
    1: {
      label: 'Beginner',
      color: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
      icon: '🌱',
    },
    2: {
      label: 'Intermediate',
      color: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
      icon: '📈',
    },
    3: {
      label: 'Advanced',
      color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
      icon: '🎯',
    },
  };

  const difficulty = difficultyConfig[course.difficulty_level as 1 | 2 | 3] ||
    difficultyConfig[1];

  const formatDuration = (minutes: number): string => {
    if (minutes < 60) return `${minutes} min`;
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
  };

  const handleStart = () => {
    router.push(`/education/course/${course.id}`);
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden hover:shadow-lg transition-shadow">
      {/* Thumbnail */}
      {course.thumbnail_url ? (
        <img
          src={course.thumbnail_url}
          alt={course.title}
          className="w-full h-48 object-cover"
        />
      ) : (
        <div className="w-full h-48 bg-gradient-to-br from-primary-500 to-primary-700 flex items-center justify-center">
          <span className="text-6xl">📚</span>
        </div>
      )}

      {/* Content */}
      <div className="p-6">
        {/* Header with Difficulty Badge */}
        <div className="flex items-start justify-between mb-3">
          <h3 className="text-xl font-bold text-gray-900 dark:text-white flex-1">
            {course.title}
          </h3>
          <span className={`px-2 py-1 rounded-md text-xs font-semibold ${difficulty.color} whitespace-nowrap ml-2`}>
            {difficulty.icon} {difficulty.label}
          </span>
        </div>

        {/* Description */}
        <p className="text-gray-600 dark:text-gray-400 text-sm mb-4 line-clamp-3">
          {course.description}
        </p>

        {/* Meta Info */}
        <div className="flex items-center gap-4 mb-4 text-sm text-gray-500 dark:text-gray-400">
          <div className="flex items-center gap-1">
            <span>⏱️</span>
            <span>{formatDuration(course.duration_minutes)}</span>
          </div>
          {course.reward_percent && (
            <div className="flex items-center gap-1 text-green-600 dark:text-green-400 font-medium">
              <span>🎁</span>
              <span>{course.reward_percent}% discount</span>
            </div>
          )}
        </div>

        {/* CTA Button */}
        <button
          onClick={handleStart}
          className="w-full px-4 py-2.5 bg-primary-500 hover:bg-primary-600 text-white font-medium rounded-lg transition-colors"
        >
          Start Course →
        </button>
      </div>
    </div>
  );
}

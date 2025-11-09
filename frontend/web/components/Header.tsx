'use client';

import Link from 'next/link';
import { Button } from '@telebot/ui';
import ThemeToggle from './ThemeToggle';

/**
 * Header Component
 *
 * Main navigation bar with logo, links, and theme toggle.
 * Responsive design with mobile menu.
 */
export default function Header() {
  return (
    <header className="sticky top-0 z-50 w-full border-b border-gray-200 dark:border-gray-800 bg-white/80 dark:bg-gray-900/80 backdrop-blur-md">
      <nav className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2">
            <span className="text-2xl">📊</span>
            <span className="font-bold text-xl text-gray-900 dark:text-white">
              TeleBot
            </span>
          </Link>

          {/* Desktop Navigation */}
          <div className="hidden md:flex items-center gap-6">
            <Link
              href="/"
              className="text-gray-700 dark:text-gray-300 hover:text-primary-500 transition-colors"
            >
              Home
            </Link>
            <Link
              href="/pricing"
              className="text-gray-700 dark:text-gray-300 hover:text-primary-500 transition-colors"
            >
              Pricing
            </Link>
            <Link
              href="/performance"
              className="text-gray-700 dark:text-gray-300 hover:text-primary-500 transition-colors"
            >
              Performance
            </Link>
            <a
              href="https://t.me/YourBot"
              target="_blank"
              rel="noopener noreferrer"
              className="text-gray-700 dark:text-gray-300 hover:text-primary-500 transition-colors"
            >
              Support
            </a>
          </div>

          {/* CTA + Theme Toggle */}
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <Link href="https://t.me/YourBot">
              <Button variant="primary" size="sm">
                Get Started
              </Button>
            </Link>
          </div>
        </div>
      </nav>
    </header>
  );
}

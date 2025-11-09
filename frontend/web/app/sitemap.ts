/**
 * Dynamic Sitemap Generator
 *
 * Generates XML sitemap for search engine crawlers with:
 * - Static pages (/, /pricing, /legal/*)
 * - Dynamic pages (blog posts, docs, performance)
 * - Priority and changefreq hints
 * - Last modified timestamps
 */

import { MetadataRoute } from 'next';

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://telebot-trading.com';

/**
 * Generate sitemap
 *
 * Next.js automatically serves this at /sitemap.xml
 *
 * @returns Sitemap entries
 */
export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  const oneWeekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
  const oneMonthAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);

  return [
    // Homepage (highest priority, changes frequently)
    {
      url: SITE_URL,
      lastModified: now,
      changeFrequency: 'daily',
      priority: 1.0,
    },

    // Pricing (high priority, changes occasionally)
    {
      url: `${SITE_URL}/pricing`,
      lastModified: oneWeekAgo,
      changeFrequency: 'weekly',
      priority: 0.9,
    },

    // Performance (high priority, changes daily)
    {
      url: `${SITE_URL}/performance`,
      lastModified: now,
      changeFrequency: 'daily',
      priority: 0.8,
    },

    // Legal Pages (medium priority, changes rarely)
    {
      url: `${SITE_URL}/legal/terms`,
      lastModified: oneMonthAgo,
      changeFrequency: 'monthly',
      priority: 0.6,
    },
    {
      url: `${SITE_URL}/legal/privacy`,
      lastModified: oneMonthAgo,
      changeFrequency: 'monthly',
      priority: 0.6,
    },
    {
      url: `${SITE_URL}/legal/risk`,
      lastModified: oneMonthAgo,
      changeFrequency: 'monthly',
      priority: 0.6,
    },
    {
      url: `${SITE_URL}/legal/cookies`,
      lastModified: oneMonthAgo,
      changeFrequency: 'monthly',
      priority: 0.6,
    },

    // Education Hub (medium priority, changes weekly)
    {
      url: `${SITE_URL}/education`,
      lastModified: oneWeekAgo,
      changeFrequency: 'weekly',
      priority: 0.7,
    },

    // Trust & Verification (medium priority)
    {
      url: `${SITE_URL}/trust`,
      lastModified: oneWeekAgo,
      changeFrequency: 'weekly',
      priority: 0.7,
    },

    // Docs (lower priority, changes occasionally)
    {
      url: `${SITE_URL}/docs`,
      lastModified: oneWeekAgo,
      changeFrequency: 'weekly',
      priority: 0.5,
    },

    // About/Company Pages (lower priority)
    {
      url: `${SITE_URL}/about`,
      lastModified: oneMonthAgo,
      changeFrequency: 'monthly',
      priority: 0.4,
    },
    {
      url: `${SITE_URL}/careers`,
      lastModified: oneMonthAgo,
      changeFrequency: 'monthly',
      priority: 0.4,
    },
    {
      url: `${SITE_URL}/contact`,
      lastModified: oneMonthAgo,
      changeFrequency: 'monthly',
      priority: 0.4,
    },
  ];
}

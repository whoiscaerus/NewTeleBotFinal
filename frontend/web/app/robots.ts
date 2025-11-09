/**
 * Robots.txt Generator
 *
 * Defines crawler rules:
 * - Allow all major search engines
 * - Block admin/API routes
 * - Point to sitemap
 */

import { MetadataRoute } from 'next';

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://telebot-trading.com';

/**
 * Generate robots.txt
 *
 * Next.js automatically serves this at /robots.txt
 *
 * @returns Robots.txt rules
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        disallow: [
          '/api/',
          '/admin/',
          '/dashboard/',
          '/_next/static/',
          '/*?variant=*', // Don't index A/B test variant URLs
        ],
      },
      {
        userAgent: 'Googlebot',
        allow: '/',
        disallow: ['/api/', '/admin/', '/dashboard/'],
      },
      {
        userAgent: 'Bingbot',
        allow: '/',
        disallow: ['/api/', '/admin/', '/dashboard/'],
      },
    ],
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}

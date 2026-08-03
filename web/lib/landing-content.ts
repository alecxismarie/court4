import {
  BarChart3,
  ClipboardList,
  CloudUpload,
  Crosshair,
  LineChart,
  MapPin,
  QrCode,
  Share2,
  Target,
  UsersRound,
  Video,
} from "lucide-react";

export const landingStatistics = [
  { value: "10K+", label: "Matches Analyzed", icon: ClipboardList },
  { value: "5K+", label: "Players Improving", icon: UsersRound },
  { value: "95%", label: "Would Recommend Court4", icon: Target },
] as const;

export const heroFeatures = [
  { label: "Performance Insights", icon: LineChart },
  { label: "Track Your Progress", icon: Crosshair },
  { label: "Share & Improve", icon: Share2 },
] as const;

export const journeySteps = [
  {
    number: 1,
    title: "Scan",
    copy: "Scan the Court4 QR code at the court to start your match.",
    icon: QrCode,
  },
  {
    number: 2,
    title: "Play",
    copy: "We record your match automatically while you focus on your game.",
    icon: Video,
  },
  {
    number: 3,
    title: "Analyze",
    copy: "Our AI analyzes every point, movement, and position on the court.",
    icon: CloudUpload,
  },
  {
    number: 4,
    title: "Insights",
    copy: "Get performance insights that reveal your strengths and opportunities.",
    icon: BarChart3,
  },
  {
    number: 5,
    title: "Improve",
    copy: "Track your progress over time and elevate every match.",
    icon: LineChart,
  },
] as const;

export const partnerClubs = [
  {
    name: "ACE Pickleball Club",
    location: "Los Angeles, CA",
    standardRate: "$60/hr",
    court4Rate: "$48/hr",
    discount: "20% OFF",
  },
  {
    name: "The Pickle Yard",
    location: "Irvine, CA",
    standardRate: "$55/hr",
    court4Rate: "$44/hr",
    discount: "20% OFF",
  },
  {
    name: "Bay Area Pickle Club",
    location: "San Jose, CA",
    standardRate: "$50/hr",
    court4Rate: "$40/hr",
    discount: "20% OFF",
  },
  {
    name: "Smash House",
    location: "San Diego, CA",
    standardRate: "$45/hr",
    court4Rate: "$36/hr",
    discount: "20% OFF",
  },
] as const;

export const footerGroups = [
  {
    title: "Product",
    links: [
      { label: "Features", href: "#features" },
      { label: "How It Works", href: "#journey" },
      { label: "Pricing", href: "#partner-clubs" },
    ],
  },
  {
    title: "For Clubs",
    links: [
      { label: "Smart Courts", href: "#partner-clubs" },
      { label: "Partner Program", href: "#partner-clubs" },
      { label: "Resources", href: "#newsletter" },
    ],
  },
  {
    title: "Company",
    links: [
      { label: "About Us", href: "#about" },
      { label: "Careers", href: "#newsletter" },
      { label: "Contact", href: "#support" },
    ],
  },
  {
    title: "Support",
    links: [
      { label: "Help Center", href: "#support" },
      { label: "Privacy Policy", href: "#legal" },
      { label: "Terms of Service", href: "#legal" },
    ],
  },
] as const;

export const mapPins = [
  { left: "26%", top: "22%" },
  { left: "15%", top: "62%" },
  { left: "52%", top: "64%" },
  { left: "79%", top: "39%" },
  { left: "70%", top: "87%" },
] as const;

export { MapPin };

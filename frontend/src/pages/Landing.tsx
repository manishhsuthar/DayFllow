import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { LandingNav } from '@/components/landing/LandingNav';
import { HeroSection } from '@/components/landing/HeroSection';
import { BenefitsSection } from '@/components/landing/BenefitsSection';
import { WaveDivider, WaveDividerAlt } from '@/components/landing/WaveDivider';
import { ReasonsSection } from '@/components/landing/ReasonsSection';
import { FeaturesSection } from '@/components/landing/FeaturesSection';
import { Footer } from '@/components/landing/Footer';

const Landing: React.FC = () => {
  const navigate = useNavigate();

  useEffect(() => {
    const isElectron = window.navigator.userAgent.indexOf('Electron') > -1 || (window as any).electronAPI !== undefined;
    if (isElectron) {
      navigate('/login', { replace: true });
    }
  }, [navigate]);

  return (
    <div className="min-h-screen bg-background">
      <LandingNav />
      
      {/* Hero Section */}
      <HeroSection />
      
      {/* Wave Divider to Benefits */}
      <WaveDivider fill="hsl(307 60% 94%)" className="-mt-1" />
      
      {/* Benefits Section */}
      <BenefitsSection />
      
      {/* Wave Divider to Reasons */}
      <WaveDividerAlt fill="hsl(0 0% 100%)" className="-mb-1" />
      
      {/* Reasons Section */}
      <ReasonsSection />
      
      {/* Wave Divider to Features */}
      <WaveDivider fill="hsl(307 60% 94%)" className="-mt-1" />
      
      {/* Features Section */}
      <FeaturesSection />
      
      {/* Wave Divider to Footer */}
      <WaveDividerAlt fill="hsl(300 56% 19%)" className="-mb-1" />
      
      {/* Footer */}
      <Footer />
    </div>
  );
};

export default Landing;

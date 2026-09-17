import React from 'react';
import { Store, Plus, RotateCcw, Sparkles } from 'lucide-react';

interface NavbarProps {
  onOpenAddModal: () => void;
  onResetData: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({ onOpenAddModal, onResetData }) => {
  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-30 shadow-xs">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Brand Logo & Shop Name */}
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-600 flex items-center justify-center text-white shadow-md shadow-emerald-200">
              <Store className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="text-xl font-bold tracking-tight text-slate-900">Ledgerly</span>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800">
                  <Sparkles className="w-3 h-3 text-emerald-600" />
                  AI Khata
                </span>
              </div>
              <p className="text-xs text-slate-500 font-medium">Shri Balaji General Store • Kirana Assistant</p>
            </div>
          </div>

          {/* Quick Actions */}
          <div className="flex items-center space-x-2 sm:space-x-3">
            <button
              onClick={onResetData}
              title="Reset to initial mock data"
              className="px-3 py-1.5 text-xs font-medium text-slate-600 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 rounded-lg flex items-center gap-1.5 transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Reset Demo</span>
            </button>
            <button
              onClick={onOpenAddModal}
              className="px-3.5 py-1.5 text-xs sm:text-sm font-semibold text-white bg-emerald-600 hover:bg-emerald-700 active:bg-emerald-800 rounded-lg shadow-sm flex items-center gap-1.5 transition-all"
            >
              <Plus className="w-4 h-4" />
              <span>Add Entry</span>
            </button>
          </div>
        </div>
      </div>
    </header>
  );
};

import React, { useState, useEffect, useRef } from 'react';
import { 
  Users, 
  UserPlus, 
  Trash2, 
  ShieldCheck, 
  Search, 
  Upload, 
  Image as ImageIcon, 
  X, 
  CheckCircle2, 
  AlertCircle,
  RefreshCw,
  Camera,
  BadgeCheck
} from 'lucide-react';
import { getPersonnelList, registerPersonnel, deletePersonnel } from '../../services/videoApi';

const PersonnelRegistry = () => {
  const [personnel, setPersonnel] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  
  // Registration Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [name, setName] = useState('');
  const [role, setRole] = useState('Authorized Personnel');
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [previewUrls, setPreviewUrls] = useState([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [modalError, setModalError] = useState('');
  const [modalSuccess, setModalSuccess] = useState('');

  const fileInputRef = useRef(null);

  // Fetch personnel list on mount
  const loadPersonnel = async () => {
    setLoading(true);
    try {
      const data = await getPersonnelList();
      setPersonnel(data.personnel || []);
    } catch (err) {
      console.error('Failed to load personnel:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPersonnel();
  }, []);

  // Handle image files selection
  const handleFileChange = (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;

    // Filter image files only
    const validImages = files.filter(f => f.type.startsWith('image/'));
    if (validImages.length + selectedFiles.length > 10) {
      setModalError('You can upload up to 10 photos maximum (3 to 5 recommended).');
      return;
    }

    setModalError('');
    const newFiles = [...selectedFiles, ...validImages];
    setSelectedFiles(newFiles);

    // Create object URLs for previews
    const newPreviews = validImages.map(file => URL.createObjectURL(file));
    setPreviewUrls(prev => [...prev, ...newPreviews]);
  };

  const handleRemovePhoto = (index) => {
    setSelectedFiles(prev => prev.filter((_, i) => i !== index));
    if (previewUrls[index]) {
      URL.revokeObjectURL(previewUrls[index]);
    }
    setPreviewUrls(prev => prev.filter((_, i) => i !== index));
  };

  const handleOpenModal = () => {
    setName('');
    setRole('Authorized Personnel');
    setSelectedFiles([]);
    setPreviewUrls([]);
    setModalError('');
    setModalSuccess('');
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    if (isSubmitting) return;
    previewUrls.forEach(url => URL.revokeObjectURL(url));
    setIsModalOpen(false);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!name.trim()) {
      setModalError('Full name is required.');
      return;
    }
    if (selectedFiles.length === 0) {
      setModalError('Please upload at least 1 photo (3 to 5 recommended for best accuracy).');
      return;
    }

    setIsSubmitting(true);
    setModalError('');
    setModalSuccess('');

    try {
      const res = await registerPersonnel(name.trim(), role.trim(), selectedFiles);
      setModalSuccess(`Successfully registered ${name}! Face embeddings active in gallery.`);
      setTimeout(() => {
        handleCloseModal();
        loadPersonnel();
      }, 1200);
    } catch (err) {
      setModalError(err.message || 'Registration failed. Ensure photos contain clear frontal faces.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (personId, personName) => {
    if (!window.confirm(`Are you sure you want to remove ${personName} from the Authorized Personnel gallery? They will immediately be classified as UNKNOWN_PERSON.`)) {
      return;
    }

    try {
      await deletePersonnel(personId);
      loadPersonnel();
    } catch (err) {
      alert(`Failed to delete person: ${err.message}`);
    }
  };

  const filteredPersonnel = personnel.filter(p => {
    if (!searchTerm) return true;
    const q = searchTerm.toLowerCase();
    return (
      p.name?.toLowerCase().includes(q) ||
      p.role?.toLowerCase().includes(q) ||
      p.person_id?.toLowerCase().includes(q)
    );
  });

  return (
    <div className="flex flex-col gap-6">
      {/* Top Header Card */}
      <div className="bg-slate-900/80 backdrop-blur-md border border-slate-800/90 rounded-xl p-5 shadow-[0_4px_25px_rgba(0,0,0,0.4)] flex flex-col md:flex-row justify-between md:items-center gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <div className="p-2 rounded bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
              <Users className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white tracking-wide flex items-center gap-2">
                PERSONNEL REGISTRY & RECOGNITION GALLERY
              </h2>
              <p className="text-xs font-mono text-slate-400">
                SFace 128-D Biometric Centroids • YuNet Neural Aligned • Autonomous Recognition
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={loadPersonnel}
            disabled={loading}
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors"
            title="Refresh Registry"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-cyan-400' : ''}`} />
          </button>

          <button
            onClick={handleOpenModal}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-medium text-xs font-mono shadow-[0_0_15px_rgba(6,182,212,0.3)] transition-all"
          >
            <UserPlus className="w-4 h-4" />
            <span>REGISTER PERSONNEL</span>
          </button>
        </div>
      </div>

      {/* Registry Metrics & Search Bar */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4 flex items-center justify-between">
          <div>
            <div className="text-[11px] font-mono text-slate-400 uppercase">Registered Personnel</div>
            <div className="text-2xl font-bold text-white font-mono mt-0.5">{personnel.length}</div>
          </div>
          <div className="p-3 rounded-lg bg-blue-500/10 text-cyan-400 border border-blue-500/20">
            <BadgeCheck className="w-5 h-5" />
          </div>
        </div>

        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4 flex items-center justify-between">
          <div>
            <div className="text-[11px] font-mono text-slate-400 uppercase">Clearance Status</div>
            <div className="text-2xl font-bold text-emerald-400 font-mono mt-0.5">ACTIVE</div>
          </div>
          <div className="p-3 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <ShieldCheck className="w-5 h-5" />
          </div>
        </div>

        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4 flex items-center justify-between">
          <div>
            <div className="text-[11px] font-mono text-slate-400 uppercase">Recognition Engine</div>
            <div className="text-2xl font-bold text-cyan-300 font-mono mt-0.5">YuNet + SFace</div>
          </div>
          <div className="p-3 rounded-lg bg-purple-500/10 text-purple-400 border border-purple-500/20">
            <Camera className="w-5 h-5" />
          </div>
        </div>
      </div>

      {/* Filter / Search Row */}
      <div className="flex items-center justify-between gap-4 bg-slate-950/40 p-2 rounded-lg border border-slate-800/60">
        <div className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search by name, role, or ID..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-slate-900/90 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500/50 font-mono"
          />
        </div>
        <div className="text-xs font-mono text-slate-500 pr-2">
          Showing {filteredPersonnel.length} of {personnel.length} records
        </div>
      </div>

      {/* Personnel Cards Grid */}
      {loading ? (
        <div className="p-12 text-center text-slate-500 font-mono flex flex-col items-center gap-2">
          <RefreshCw className="w-6 h-6 animate-spin text-cyan-400" />
          <span>Synchronizing Personnel Registry from Database...</span>
        </div>
      ) : filteredPersonnel.length === 0 ? (
        <div className="bg-slate-900/40 border border-slate-800/80 rounded-xl p-12 text-center text-slate-500 font-mono flex flex-col items-center gap-3">
          <Users className="w-10 h-10 text-slate-600" />
          <div className="text-sm font-semibold text-slate-300">No Personnel Registered</div>
          <div className="text-xs text-slate-500 max-w-sm">
            Click "REGISTER PERSONNEL" to upload 3–5 face portrait photos and activate biometric recognition for authorized personnel.
          </div>
          <button
            onClick={handleOpenModal}
            className="mt-2 flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600/30 hover:bg-blue-600/50 text-cyan-300 border border-blue-500/40 text-xs font-mono transition-all"
          >
            <UserPlus className="w-4 h-4" />
            <span>Register First Person</span>
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filteredPersonnel.map((person) => {
            const hasPhotos = person.photos && person.photos.length > 0;
            const primaryPhotoUrl = hasPhotos 
              ? `/api/v1/faces/${person.person_id}/photo/${person.photos[0]}`
              : null;

            return (
              <div 
                key={person.person_id}
                className="bg-slate-900/80 backdrop-blur-md border border-slate-800 hover:border-cyan-500/40 rounded-xl overflow-hidden shadow-lg transition-all duration-200 flex flex-col justify-between group"
              >
                {/* Photo and Badge header */}
                <div className="p-4 flex items-start gap-3">
                  <div className="relative w-14 h-14 rounded-lg bg-slate-950 border border-slate-800 overflow-hidden shrink-0">
                    {primaryPhotoUrl ? (
                      <img 
                        src={primaryPhotoUrl} 
                        alt={person.name} 
                        className="w-full h-full object-cover"
                        onError={(e) => {
                          e.target.style.display = 'none';
                        }}
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-slate-600">
                        <Users className="w-6 h-6" />
                      </div>
                    )}
                    <span className="absolute bottom-0 right-0 w-3 h-3 bg-emerald-500 rounded-tl border-t border-l border-slate-950" title="Active in Gallery" />
                  </div>

                  <div className="flex-1 min-w-0">
                    <h4 className="text-sm font-bold text-white truncate font-sans group-hover:text-cyan-300 transition-colors">
                      {person.name}
                    </h4>
                    <div className="text-[11px] font-mono text-cyan-400/90 truncate">
                      {person.role || 'Authorized Personnel'}
                    </div>
                    <div className="text-[10px] font-mono text-slate-500 mt-1">
                      ID: {person.person_id}
                    </div>
                  </div>
                </div>

                {/* Details Footer */}
                <div className="px-4 py-3 bg-slate-950/60 border-t border-slate-800/80 flex items-center justify-between text-[11px] font-mono text-slate-400">
                  <div className="flex items-center gap-1.5">
                    <ImageIcon className="w-3.5 h-3.5 text-slate-500" />
                    <span>{person.photos_count || person.photos?.length || 1} photo(s)</span>
                  </div>

                  <button
                    onClick={() => handleDelete(person.person_id, person.name)}
                    className="p-1.5 rounded hover:bg-red-500/20 text-slate-500 hover:text-red-400 transition-colors"
                    title="Remove from Recognition Gallery"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Registration Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-md w-full overflow-hidden shadow-2xl animate-in fade-in zoom-in-95 duration-200">
            {/* Modal Header */}
            <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
              <div className="flex items-center gap-2">
                <UserPlus className="w-4 h-4 text-cyan-400" />
                <h3 className="font-mono font-bold text-sm text-white uppercase">Register Authorized Personnel</h3>
              </div>
              <button
                onClick={handleCloseModal}
                disabled={isSubmitting}
                className="p-1 rounded text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Form */}
            <form onSubmit={handleSubmit} className="p-5 space-y-4">
              {modalError && (
                <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs font-mono flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                  <span>{modalError}</span>
                </div>
              )}

              {modalSuccess && (
                <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-mono flex items-start gap-2">
                  <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
                  <span>{modalSuccess}</span>
                </div>
              )}

              <div>
                <label className="block text-xs font-mono font-semibold text-slate-300 uppercase mb-1">
                  Full Name *
                </label>
                <input
                  type="text"
                  placeholder="e.g. Major Vikram Rathore"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  disabled={isSubmitting}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-cyan-500 font-mono"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-mono font-semibold text-slate-300 uppercase mb-1">
                  Role / Designation
                </label>
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  disabled={isSubmitting}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500 font-mono"
                >
                  <option value="Authorized Personnel">Authorized Personnel</option>
                  <option value="Border Security Officer">Border Security Officer</option>
                  <option value="Squad Leader">Squad Leader</option>
                  <option value="Command Staff">Command Staff</option>
                  <option value="Technical Engineer">Technical Engineer</option>
                  <option value="Defense Contractor">Defense Contractor</option>
                </select>
              </div>

              {/* Photo Upload Area */}
              <div>
                <label className="block text-xs font-mono font-semibold text-slate-300 uppercase mb-1">
                  Portrait Photos (3 to 5 Recommended) *
                </label>
                <div 
                  onClick={() => fileInputRef.current?.click()}
                  className="border-2 border-dashed border-slate-800 hover:border-cyan-500/50 rounded-xl p-4 text-center cursor-pointer bg-slate-950/40 transition-colors"
                >
                  <Upload className="w-6 h-6 text-slate-500 mx-auto mb-1" />
                  <span className="text-xs font-mono text-slate-300 font-medium block">
                    Click to select 3–5 face photos
                  </span>
                  <span className="text-[10px] font-mono text-slate-500 block mt-0.5">
                    JPG, JPEG, PNG (Frontal face portraits with clear lighting)
                  </span>
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept="image/jpeg,image/png,image/jpg"
                    onChange={handleFileChange}
                    className="hidden"
                    disabled={isSubmitting}
                  />
                </div>

                {/* Previews */}
                {previewUrls.length > 0 && (
                  <div className="grid grid-cols-4 gap-2 mt-3">
                    {previewUrls.map((url, idx) => (
                      <div key={idx} className="relative group rounded-lg overflow-hidden border border-slate-700 aspect-square bg-slate-950">
                        <img src={url} alt={`preview ${idx}`} className="w-full h-full object-cover" />
                        <button
                          type="button"
                          onClick={() => handleRemovePhoto(idx)}
                          disabled={isSubmitting}
                          className="absolute top-1 right-1 p-1 bg-black/70 hover:bg-red-600 rounded-full text-white opacity-0 group-hover:opacity-100 transition-opacity"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Modal Actions */}
              <div className="pt-3 border-t border-slate-800/80 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={handleCloseModal}
                  disabled={isSubmitting}
                  className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-mono text-xs transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-mono text-xs font-semibold shadow-lg transition-all"
                >
                  {isSubmitting ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      <span>Generating Embeddings...</span>
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>Save & Activate</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default PersonnelRegistry;

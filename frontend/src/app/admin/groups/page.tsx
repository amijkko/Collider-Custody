'use client';

import * as React from 'react';
import {
  Users,
  Shield,
  Plus,
  Trash2,
  RefreshCw,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Database,
} from 'lucide-react';
import { Header, PageContainer } from '@/components/layout/header';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge, StatusBadge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/modal';
import { useToastHelpers } from '@/hooks/use-toast';
import { groupsApi } from '@/lib/api';
import { formatAddress, formatRelativeTime } from '@/lib/utils';
import { Group, AddressBookEntry, PolicySet, AddressKind } from '@/types';

export default function GroupsPage() {
  const toast = useToastHelpers();
  const [groups, setGroups] = React.useState<Group[]>([]);
  const [selectedGroup, setSelectedGroup] = React.useState<Group | null>(null);
  const [addresses, setAddresses] = React.useState<AddressBookEntry[]>([]);
  const [policies, setPolicies] = React.useState<PolicySet[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [isSeeding, setIsSeeding] = React.useState(false);

  // Add address modal
  const [showAddAddress, setShowAddAddress] = React.useState(false);
  const [newAddress, setNewAddress] = React.useState('');
  const [newAddressKind, setNewAddressKind] = React.useState<AddressKind>('ALLOW');
  const [newAddressLabel, setNewAddressLabel] = React.useState('');
  const [isAddingAddress, setIsAddingAddress] = React.useState(false);

  const loadData = React.useCallback(async () => {
    try {
      const [groupsRes, policiesRes] = await Promise.all([
        groupsApi.list(),
        groupsApi.listPolicies().catch(() => ({ data: { policy_sets: [] } })),
      ]);
      setGroups(groupsRes.data.groups);
      setPolicies(policiesRes.data.policy_sets);

      // Auto-select first group if none selected
      if (!selectedGroup && groupsRes.data.groups.length > 0) {
        setSelectedGroup(groupsRes.data.groups[0]);
      }
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setIsLoading(false);
    }
  }, [selectedGroup]);

  const loadAddresses = React.useCallback(async () => {
    if (!selectedGroup) return;
    try {
      const res = await groupsApi.listAddresses(selectedGroup.id);
      setAddresses(res.data.entries);
    } catch (error) {
      console.error('Failed to load addresses:', error);
    }
  }, [selectedGroup]);

  React.useEffect(() => {
    loadData();
  }, []);

  React.useEffect(() => {
    if (selectedGroup) {
      loadAddresses();
    }
  }, [selectedGroup, loadAddresses]);

  const handleSeedData = async () => {
    setIsSeeding(true);
    try {
      await groupsApi.seed();
      toast.success('Demo data seeded', 'Retail group and policies created');
      loadData();
    } catch (error) {
      toast.error('Failed to seed data', error instanceof Error ? error.message : 'Please try again');
    } finally {
      setIsSeeding(false);
    }
  };

  const handleAddAddress = async () => {
    if (!selectedGroup || !newAddress) return;

    setIsAddingAddress(true);
    try {
      await groupsApi.addAddress(selectedGroup.id, {
        address: newAddress,
        kind: newAddressKind,
        label: newAddressLabel || undefined,
      });
      toast.success('Address added', `Added to ${newAddressKind.toLowerCase()}list`);
      setShowAddAddress(false);
      setNewAddress('');
      setNewAddressLabel('');
      loadAddresses();
      loadData(); // Refresh counts
    } catch (error) {
      toast.error('Failed to add address', error instanceof Error ? error.message : 'Please try again');
    } finally {
      setIsAddingAddress(false);
    }
  };

  const handleRemoveAddress = async (address: string) => {
    if (!selectedGroup) return;

    try {
      await groupsApi.removeAddress(selectedGroup.id, address);
      toast.success('Address removed');
      loadAddresses();
      loadData();
    } catch (error) {
      toast.error('Failed to remove address');
    }
  };

  const getAddressIcon = (kind: AddressKind) => {
    return kind === 'ALLOW' ? (
      <CheckCircle2 className="h-4 w-4 text-emerald-400" />
    ) : (
      <XCircle className="h-4 w-4 text-red-400" />
    );
  };

  return (
    <>
      <Header
        title="Groups & Policies"
        subtitle="Manage user groups, address books, and policy sets"
        actions={
          <div className="flex items-center gap-2">
            <Button onClick={handleSeedData} variant="outline" isLoading={isSeeding}>
              <Database className="h-4 w-4 mr-2" />
              Seed Demo Data
            </Button>
            <Button onClick={() => loadData()} variant="ghost" size="icon">
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        }
      />

      <PageContainer>
        <div className="grid grid-cols-3 gap-6 animate-stagger">
          {/* Groups List */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Users className="h-5 w-5 text-brand-400" />
                Groups
              </CardTitle>
              <CardDescription>User groups with assigned policies</CardDescription>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="flex justify-center py-8">
                  <div className="animate-spin rounded-full h-6 w-6 border-t-2 border-b-2 border-brand-500"></div>
                </div>
              ) : groups.length > 0 ? (
                <div className="space-y-2">
                  {groups.map((group) => (
                    <button
                      key={group.id}
                      onClick={() => setSelectedGroup(group)}
                      className={`w-full text-left p-4 rounded-lg transition-colors ${
                        selectedGroup?.id === group.id
                          ? 'bg-brand-500/10 border border-brand-500/30'
                          : 'bg-surface-800/50 hover:bg-surface-800'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-medium text-surface-200">{group.name}</span>
                        {group.is_default && (
                          <Badge variant="primary">Default</Badge>
                        )}
                      </div>
                      <div className="flex items-center gap-4 text-xs text-surface-500">
                        <span>{group.member_count} members</span>
                        <span>{group.allowlist_count} allowlist</span>
                        <span>{group.denylist_count} denylist</span>
                      </div>
                      {group.policy_set_name && (
                        <div className="mt-2">
                          <Badge variant="outline">{group.policy_set_name}</Badge>
                        </div>
                      )}
                    </button>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8">
                  <AlertTriangle className="h-8 w-8 text-amber-400 mx-auto mb-2" />
                  <p className="text-surface-400 mb-4">No groups found</p>
                  <Button onClick={handleSeedData} variant="outline" size="sm">
                    Seed Demo Data
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Address Book */}
          <Card className="col-span-2">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <Shield className="h-5 w-5 text-brand-400" />
                    Address Book
                    {selectedGroup && (
                      <span className="text-surface-500 font-normal">- {selectedGroup.name}</span>
                    )}
                  </CardTitle>
                  <CardDescription>Allowlist and denylist addresses</CardDescription>
                </div>
                {selectedGroup && (
                  <Button onClick={() => setShowAddAddress(true)} size="sm">
                    <Plus className="h-4 w-4 mr-2" />
                    Add Address
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent>
              {!selectedGroup ? (
                <div className="text-center py-8 text-surface-500">
                  Select a group to view its address book
                </div>
              ) : addresses.length > 0 ? (
                <div className="space-y-2">
                  {addresses.map((entry) => (
                    <div
                      key={entry.id}
                      className="flex items-center justify-between p-4 rounded-lg bg-surface-800/50"
                    >
                      <div className="flex items-center gap-3">
                        {getAddressIcon(entry.kind)}
                        <div>
                          <p className="font-mono text-sm text-surface-200">{entry.address}</p>
                          {entry.label && (
                            <p className="text-xs text-surface-500">{entry.label}</p>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <Badge variant={entry.kind === 'ALLOW' ? 'success' : 'destructive'}>
                          {entry.kind}
                        </Badge>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleRemoveAddress(entry.address)}
                          className="text-surface-500 hover:text-red-400"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-surface-500">
                  No addresses in this group's address book
                </div>
              )}
            </CardContent>
          </Card>

          {/* Policy Sets */}
          <Card className="col-span-3">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Shield className="h-5 w-5 text-purple-400" />
                Policy Sets
              </CardTitle>
              <CardDescription>Available policy sets with rules</CardDescription>
            </CardHeader>
            <CardContent>
              {policies.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-surface-800">
                        <th className="text-left py-3 px-4 text-sm font-medium text-surface-400">Name</th>
                        <th className="text-left py-3 px-4 text-sm font-medium text-surface-400">Version</th>
                        <th className="text-left py-3 px-4 text-sm font-medium text-surface-400">Description</th>
                        <th className="text-left py-3 px-4 text-sm font-medium text-surface-400">Status</th>
                        <th className="text-left py-3 px-4 text-sm font-medium text-surface-400">Hash</th>
                      </tr>
                    </thead>
                    <tbody>
                      {policies.map((policy) => (
                        <tr key={policy.id} className="border-b border-surface-800/50 hover:bg-surface-800/30">
                          <td className="py-3 px-4 text-surface-200 font-medium">{policy.name}</td>
                          <td className="py-3 px-4 text-surface-400">v{policy.version}</td>
                          <td className="py-3 px-4 text-surface-400 max-w-md truncate">
                            {policy.description}
                          </td>
                          <td className="py-3 px-4">
                            <Badge variant={policy.is_active ? 'success' : 'default'}>
                              {policy.is_active ? 'Active' : 'Inactive'}
                            </Badge>
                          </td>
                          <td className="py-3 px-4 font-mono text-xs text-surface-500">
                            {policy.snapshot_hash ? policy.snapshot_hash.substring(0, 16) + '...' : '-'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-center py-8 text-surface-500">
                  No policy sets found. Seed demo data to create the Retail policy.
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </PageContainer>

      {/* Add Address Dialog */}
      <Dialog open={showAddAddress} onOpenChange={setShowAddAddress}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Address to {selectedGroup?.name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <Input
              label="Ethereum Address"
              placeholder="0x..."
              value={newAddress}
              onChange={(e) => setNewAddress(e.target.value)}
            />
            <div className="space-y-1.5">
              <label className="block text-sm font-medium text-surface-300">Type</label>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setNewAddressKind('ALLOW')}
                  className={`flex-1 py-2 px-4 rounded-lg border transition-colors ${
                    newAddressKind === 'ALLOW'
                      ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                      : 'bg-surface-800 border-surface-700 text-surface-400'
                  }`}
                >
                  <CheckCircle2 className="h-4 w-4 inline mr-2" />
                  Allowlist
                </button>
                <button
                  type="button"
                  onClick={() => setNewAddressKind('DENY')}
                  className={`flex-1 py-2 px-4 rounded-lg border transition-colors ${
                    newAddressKind === 'DENY'
                      ? 'bg-red-500/10 border-red-500/30 text-red-400'
                      : 'bg-surface-800 border-surface-700 text-surface-400'
                  }`}
                >
                  <XCircle className="h-4 w-4 inline mr-2" />
                  Denylist
                </button>
              </div>
            </div>
            <Input
              label="Label (optional)"
              placeholder="e.g., Binance Hot Wallet"
              value={newAddressLabel}
              onChange={(e) => setNewAddressLabel(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setShowAddAddress(false)}>
              Cancel
            </Button>
            <Button onClick={handleAddAddress} isLoading={isAddingAddress}>
              Add Address
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

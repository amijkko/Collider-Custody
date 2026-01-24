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
  Edit2,
  ArrowRight,
  Pause,
} from 'lucide-react';
import { Header, PageContainer } from '@/components/layout/header';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '@/components/ui/modal';
import { useToastHelpers } from '@/hooks/use-toast';
import { groupsApi } from '@/lib/api';
import { Group, AddressBookEntry, PolicySet, PolicyRule, AddressKind, PolicyDecision } from '@/types';

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

  // Policy editor modals
  const [showCreatePolicy, setShowCreatePolicy] = React.useState(false);
  const [showEditPolicy, setShowEditPolicy] = React.useState(false);
  const [showRuleEditor, setShowRuleEditor] = React.useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = React.useState(false);
  const [selectedPolicy, setSelectedPolicy] = React.useState<PolicySet | null>(null);
  const [editingRule, setEditingRule] = React.useState<PolicyRule | null>(null);

  // Create policy form
  const [newPolicyName, setNewPolicyName] = React.useState('');
  const [newPolicyDescription, setNewPolicyDescription] = React.useState('');
  const [isCreatingPolicy, setIsCreatingPolicy] = React.useState(false);

  // Edit policy form
  const [editPolicyName, setEditPolicyName] = React.useState('');
  const [editPolicyDescription, setEditPolicyDescription] = React.useState('');
  const [editPolicyActive, setEditPolicyActive] = React.useState(true);
  const [isSavingPolicy, setIsSavingPolicy] = React.useState(false);
  const [isDeletingPolicy, setIsDeletingPolicy] = React.useState(false);

  // Rule editor form
  const [ruleId, setRuleId] = React.useState('');
  const [rulePriority, setRulePriority] = React.useState(100);
  const [ruleDecision, setRuleDecision] = React.useState<PolicyDecision>('ALLOW');
  const [ruleAmountOp, setRuleAmountOp] = React.useState<string>('');
  const [ruleAmountValue, setRuleAmountValue] = React.useState('');
  const [ruleAddressStatus, setRuleAddressStatus] = React.useState<string>('');
  const [ruleKytRequired, setRuleKytRequired] = React.useState(true);
  const [ruleApprovalRequired, setRuleApprovalRequired] = React.useState(false);
  const [ruleApprovalCount, setRuleApprovalCount] = React.useState(0);
  const [ruleDescription, setRuleDescription] = React.useState('');
  const [isSavingRule, setIsSavingRule] = React.useState(false);

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

  const loadPolicyDetails = React.useCallback(async (policyId: string) => {
    try {
      const res = await groupsApi.getPolicy(policyId);
      setSelectedPolicy(res.data);
      // Update in policies list
      setPolicies(prev => prev.map(p => p.id === policyId ? res.data : p));
    } catch (error) {
      console.error('Failed to load policy details:', error);
    }
  }, []);

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
      loadData();
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

  // Policy handlers
  const handleCreatePolicy = async () => {
    if (!newPolicyName) return;

    setIsCreatingPolicy(true);
    try {
      await groupsApi.createPolicy({
        name: newPolicyName,
        description: newPolicyDescription || undefined,
      });
      toast.success('Policy created', `${newPolicyName} v1 created`);
      setShowCreatePolicy(false);
      setNewPolicyName('');
      setNewPolicyDescription('');
      loadData();
    } catch (error) {
      toast.error('Failed to create policy', error instanceof Error ? error.message : 'Please try again');
    } finally {
      setIsCreatingPolicy(false);
    }
  };

  const handleEditPolicy = async (policy: PolicySet) => {
    await loadPolicyDetails(policy.id);
    setEditPolicyName(policy.name);
    setEditPolicyDescription(policy.description || '');
    setEditPolicyActive(policy.is_active);
    setShowEditPolicy(true);
  };

  const handleSavePolicy = async () => {
    if (!selectedPolicy) return;

    setIsSavingPolicy(true);
    try {
      await groupsApi.updatePolicy(selectedPolicy.id, {
        name: editPolicyName,
        description: editPolicyDescription,
        is_active: editPolicyActive,
      });
      toast.success('Policy updated');
      loadData();
      await loadPolicyDetails(selectedPolicy.id);
    } catch (error) {
      toast.error('Failed to update policy', error instanceof Error ? error.message : 'Please try again');
    } finally {
      setIsSavingPolicy(false);
    }
  };

  const handleDeletePolicy = async () => {
    if (!selectedPolicy) return;

    setIsDeletingPolicy(true);
    try {
      await groupsApi.deletePolicy(selectedPolicy.id);
      toast.success('Policy deleted');
      setShowDeleteConfirm(false);
      setShowEditPolicy(false);
      setSelectedPolicy(null);
      loadData();
    } catch (error) {
      toast.error('Cannot delete policy', 'Policy may be assigned to a group');
    } finally {
      setIsDeletingPolicy(false);
    }
  };

  // Rule handlers
  const openRuleEditor = (rule?: PolicyRule) => {
    if (rule) {
      setEditingRule(rule);
      setRuleId(rule.rule_id);
      setRulePriority(rule.priority);
      setRuleDecision(rule.decision);
      setRuleKytRequired(rule.kyt_required);
      setRuleApprovalRequired(rule.approval_required);
      setRuleApprovalCount(rule.approval_count);
      setRuleDescription(rule.description || '');

      // Parse conditions
      const cond = rule.conditions || {};
      if (cond.amount_lte !== undefined) {
        setRuleAmountOp('lte');
        setRuleAmountValue(String(cond.amount_lte));
      } else if (cond.amount_lt !== undefined) {
        setRuleAmountOp('lt');
        setRuleAmountValue(String(cond.amount_lt));
      } else if (cond.amount_gte !== undefined) {
        setRuleAmountOp('gte');
        setRuleAmountValue(String(cond.amount_gte));
      } else if (cond.amount_gt !== undefined) {
        setRuleAmountOp('gt');
        setRuleAmountValue(String(cond.amount_gt));
      } else {
        setRuleAmountOp('');
        setRuleAmountValue('');
      }
      setRuleAddressStatus(cond.address_in || '');
    } else {
      setEditingRule(null);
      setRuleId('');
      setRulePriority(100);
      setRuleDecision('ALLOW');
      setRuleAmountOp('');
      setRuleAmountValue('');
      setRuleAddressStatus('');
      setRuleKytRequired(true);
      setRuleApprovalRequired(false);
      setRuleApprovalCount(0);
      setRuleDescription('');
    }
    setShowRuleEditor(true);
  };

  const handleSaveRule = async () => {
    if (!selectedPolicy || !ruleId) return;

    setIsSavingRule(true);
    try {
      // Build conditions
      const conditions: Record<string, any> = {};
      if (ruleAmountOp && ruleAmountValue) {
        const amountNum = parseFloat(ruleAmountValue);
        if (ruleAmountOp === 'lte') conditions.amount_lte = amountNum;
        else if (ruleAmountOp === 'lt') conditions.amount_lt = amountNum;
        else if (ruleAmountOp === 'gte') conditions.amount_gte = amountNum;
        else if (ruleAmountOp === 'gt') conditions.amount_gt = amountNum;
      }
      if (ruleAddressStatus) {
        conditions.address_in = ruleAddressStatus;
      }

      if (editingRule) {
        // Update existing rule
        await groupsApi.updateRule(selectedPolicy.id, editingRule.rule_id, {
          priority: rulePriority,
          conditions,
          decision: ruleDecision,
          kyt_required: ruleKytRequired,
          approval_required: ruleApprovalRequired,
          approval_count: ruleApprovalCount,
          description: ruleDescription || undefined,
        });
        toast.success('Rule updated');
      } else {
        // Create new rule
        await groupsApi.addRule(selectedPolicy.id, {
          rule_id: ruleId,
          priority: rulePriority,
          conditions,
          decision: ruleDecision,
          kyt_required: ruleKytRequired,
          approval_required: ruleApprovalRequired,
          approval_count: ruleApprovalCount,
          description: ruleDescription || undefined,
        });
        toast.success('Rule added');
      }

      setShowRuleEditor(false);
      await loadPolicyDetails(selectedPolicy.id);
      loadData();
    } catch (error) {
      toast.error('Failed to save rule', error instanceof Error ? error.message : 'Please try again');
    } finally {
      setIsSavingRule(false);
    }
  };

  const handleDeleteRule = async (rule: PolicyRule) => {
    if (!selectedPolicy) return;

    try {
      await groupsApi.deleteRule(selectedPolicy.id, rule.rule_id);
      toast.success('Rule deleted');
      await loadPolicyDetails(selectedPolicy.id);
      loadData();
    } catch (error) {
      toast.error('Failed to delete rule');
    }
  };

  const getAddressIcon = (kind: AddressKind) => {
    return kind === 'ALLOW' ? (
      <CheckCircle2 className="h-4 w-4 text-emerald-400" />
    ) : (
      <XCircle className="h-4 w-4 text-red-400" />
    );
  };

  const getDecisionBadge = (decision: PolicyDecision) => {
    switch (decision) {
      case 'ALLOW':
        return <Badge variant="success">ALLOW</Badge>;
      case 'BLOCK':
        return <Badge variant="destructive">BLOCK</Badge>;
      case 'CONTINUE':
        return <Badge variant="outline">CONTINUE</Badge>;
    }
  };

  const formatConditions = (conditions: Record<string, any>) => {
    const parts: string[] = [];
    if (conditions.amount_lte !== undefined) parts.push(`≤${conditions.amount_lte} ETH`);
    if (conditions.amount_lt !== undefined) parts.push(`<${conditions.amount_lt} ETH`);
    if (conditions.amount_gte !== undefined) parts.push(`≥${conditions.amount_gte} ETH`);
    if (conditions.amount_gt !== undefined) parts.push(`>${conditions.amount_gt} ETH`);
    if (conditions.address_in) parts.push(conditions.address_in);
    return parts.length > 0 ? parts.join(', ') : 'any';
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
                <div className="space-y-2 max-h-80 overflow-y-auto">
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
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <Shield className="h-5 w-5 text-purple-400" />
                    Policy Sets
                  </CardTitle>
                  <CardDescription>Available policy sets with rules</CardDescription>
                </div>
                <Button onClick={() => setShowCreatePolicy(true)} size="sm">
                  <Plus className="h-4 w-4 mr-2" />
                  Create Policy
                </Button>
              </div>
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
                        <th className="text-right py-3 px-4 text-sm font-medium text-surface-400">Actions</th>
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
                          <td className="py-3 px-4 text-right">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleEditPolicy(policy)}
                            >
                              <Edit2 className="h-4 w-4 mr-1" />
                              Edit
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-center py-8 text-surface-500">
                  No policy sets found. Seed demo data or create a new policy.
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

      {/* Create Policy Dialog */}
      <Dialog open={showCreatePolicy} onOpenChange={setShowCreatePolicy}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Policy Set</DialogTitle>
            <DialogDescription>Create a new policy set to assign to groups</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <Input
              label="Policy Name"
              placeholder="e.g., VIP Policy"
              value={newPolicyName}
              onChange={(e) => setNewPolicyName(e.target.value)}
            />
            <div className="space-y-1.5">
              <label className="block text-sm font-medium text-surface-300">Description</label>
              <textarea
                className="w-full px-3 py-2 rounded-lg bg-surface-800 border border-surface-700 text-surface-200 placeholder:text-surface-500 focus:outline-none focus:ring-2 focus:ring-brand-500/50"
                placeholder="Description of the policy set..."
                rows={3}
                value={newPolicyDescription}
                onChange={(e) => setNewPolicyDescription(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setShowCreatePolicy(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreatePolicy} isLoading={isCreatingPolicy} disabled={!newPolicyName}>
              Create Policy
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Policy Dialog */}
      <Dialog open={showEditPolicy} onOpenChange={setShowEditPolicy}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Edit Policy: {selectedPolicy?.name} v{selectedPolicy?.version}</DialogTitle>
          </DialogHeader>
          <div className="space-y-6 py-4">
            {/* Policy Details */}
            <div className="grid grid-cols-2 gap-4">
              <Input
                label="Policy Name"
                value={editPolicyName}
                onChange={(e) => setEditPolicyName(e.target.value)}
              />
              <div className="space-y-1.5">
                <label className="block text-sm font-medium text-surface-300">Status</label>
                <button
                  type="button"
                  onClick={() => setEditPolicyActive(!editPolicyActive)}
                  className={`w-full py-2 px-4 rounded-lg border transition-colors ${
                    editPolicyActive
                      ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                      : 'bg-surface-800 border-surface-700 text-surface-400'
                  }`}
                >
                  {editPolicyActive ? (
                    <>
                      <CheckCircle2 className="h-4 w-4 inline mr-2" />
                      Active
                    </>
                  ) : (
                    <>
                      <Pause className="h-4 w-4 inline mr-2" />
                      Inactive
                    </>
                  )}
                </button>
              </div>
            </div>
            <div className="space-y-1.5">
              <label className="block text-sm font-medium text-surface-300">Description</label>
              <textarea
                className="w-full px-3 py-2 rounded-lg bg-surface-800 border border-surface-700 text-surface-200 placeholder:text-surface-500 focus:outline-none focus:ring-2 focus:ring-brand-500/50"
                rows={2}
                value={editPolicyDescription}
                onChange={(e) => setEditPolicyDescription(e.target.value)}
              />
            </div>

            {/* Rules */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium text-surface-300">Rules</h3>
                <Button size="sm" onClick={() => openRuleEditor()}>
                  <Plus className="h-4 w-4 mr-1" />
                  Add Rule
                </Button>
              </div>
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {selectedPolicy?.rules && selectedPolicy.rules.length > 0 ? (
                  selectedPolicy.rules.map((rule) => (
                    <div
                      key={rule.id}
                      className="flex items-center justify-between p-3 rounded-lg bg-surface-800/50 border border-surface-700"
                    >
                      <div className="flex items-center gap-3">
                        <span className="font-mono text-xs text-surface-500">P{rule.priority}</span>
                        <span className="font-medium text-surface-200">{rule.rule_id}</span>
                        <span className="text-surface-400 text-sm">{formatConditions(rule.conditions)}</span>
                        <ArrowRight className="h-4 w-4 text-surface-500" />
                        {getDecisionBadge(rule.decision)}
                        {rule.kyt_required && <Badge variant="outline">KYT</Badge>}
                        {rule.approval_required && <Badge variant="outline">{rule.approval_count} approvals</Badge>}
                      </div>
                      <div className="flex items-center gap-2">
                        <Button variant="ghost" size="icon" onClick={() => openRuleEditor(rule)}>
                          <Edit2 className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon" onClick={() => handleDeleteRule(rule)} className="text-red-400 hover:text-red-300">
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="text-center py-4 text-surface-500">
                    No rules defined. Add rules to define policy behavior.
                  </div>
                )}
              </div>
            </div>
          </div>
          <DialogFooter className="flex justify-between">
            <Button variant="destructive" onClick={() => setShowDeleteConfirm(true)}>
              <Trash2 className="h-4 w-4 mr-2" />
              Delete Policy
            </Button>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => setShowEditPolicy(false)}>
                Close
              </Button>
              <Button onClick={handleSavePolicy} isLoading={isSavingPolicy}>
                Save Changes
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Rule Editor Dialog */}
      <Dialog open={showRuleEditor} onOpenChange={setShowRuleEditor}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingRule ? 'Edit Rule' : 'Add Rule'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="grid grid-cols-2 gap-4">
              <Input
                label="Rule ID"
                placeholder="e.g., RET-04"
                value={ruleId}
                onChange={(e) => setRuleId(e.target.value.toUpperCase())}
                disabled={!!editingRule}
              />
              <Input
                label="Priority"
                type="number"
                value={rulePriority}
                onChange={(e) => setRulePriority(parseInt(e.target.value) || 100)}
              />
            </div>

            <div className="space-y-1.5">
              <label className="block text-sm font-medium text-surface-300">Decision</label>
              <div className="flex gap-2">
                {(['ALLOW', 'BLOCK', 'CONTINUE'] as PolicyDecision[]).map((d) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => setRuleDecision(d)}
                    className={`flex-1 py-2 px-4 rounded-lg border transition-colors ${
                      ruleDecision === d
                        ? d === 'ALLOW'
                          ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                          : d === 'BLOCK'
                          ? 'bg-red-500/10 border-red-500/30 text-red-400'
                          : 'bg-blue-500/10 border-blue-500/30 text-blue-400'
                        : 'bg-surface-800 border-surface-700 text-surface-400'
                    }`}
                  >
                    {d}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-3 p-4 rounded-lg bg-surface-800/50 border border-surface-700">
              <h4 className="text-sm font-medium text-surface-300">Conditions</h4>
              <div className="grid grid-cols-3 gap-2">
                <select
                  className="px-3 py-2 rounded-lg bg-surface-800 border border-surface-700 text-surface-200"
                  value={ruleAmountOp}
                  onChange={(e) => setRuleAmountOp(e.target.value)}
                >
                  <option value="">Any amount</option>
                  <option value="lte">Amount ≤</option>
                  <option value="lt">Amount &lt;</option>
                  <option value="gte">Amount ≥</option>
                  <option value="gt">Amount &gt;</option>
                </select>
                {ruleAmountOp && (
                  <Input
                    placeholder="0.01"
                    value={ruleAmountValue}
                    onChange={(e) => setRuleAmountValue(e.target.value)}
                  />
                )}
                <span className="flex items-center text-surface-400">{ruleAmountOp && 'ETH'}</span>
              </div>
              <select
                className="w-full px-3 py-2 rounded-lg bg-surface-800 border border-surface-700 text-surface-200"
                value={ruleAddressStatus}
                onChange={(e) => setRuleAddressStatus(e.target.value)}
              >
                <option value="">Any address status</option>
                <option value="allowlist">Allowlist only</option>
                <option value="denylist">Denylist only</option>
                <option value="unknown">Unknown only</option>
              </select>
            </div>

            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={ruleKytRequired}
                  onChange={(e) => setRuleKytRequired(e.target.checked)}
                  className="w-4 h-4 rounded border-surface-600 bg-surface-800 text-brand-500"
                />
                <span className="text-sm text-surface-300">KYT Required</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={ruleApprovalRequired}
                  onChange={(e) => setRuleApprovalRequired(e.target.checked)}
                  className="w-4 h-4 rounded border-surface-600 bg-surface-800 text-brand-500"
                />
                <span className="text-sm text-surface-300">Approval Required</span>
              </label>
              {ruleApprovalRequired && (
                <Input
                  type="number"
                  value={ruleApprovalCount}
                  onChange={(e) => setRuleApprovalCount(parseInt(e.target.value) || 0)}
                  className="w-20"
                />
              )}
            </div>

            <div className="space-y-1.5">
              <label className="block text-sm font-medium text-surface-300">Description</label>
              <textarea
                className="w-full px-3 py-2 rounded-lg bg-surface-800 border border-surface-700 text-surface-200 placeholder:text-surface-500 focus:outline-none focus:ring-2 focus:ring-brand-500/50"
                placeholder="Describe what this rule does..."
                rows={2}
                value={ruleDescription}
                onChange={(e) => setRuleDescription(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setShowRuleEditor(false)}>
              Cancel
            </Button>
            <Button onClick={handleSaveRule} isLoading={isSavingRule} disabled={!ruleId}>
              {editingRule ? 'Save Rule' : 'Add Rule'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Policy Set</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete "{selectedPolicy?.name} v{selectedPolicy?.version}"?
              This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setShowDeleteConfirm(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDeletePolicy} isLoading={isDeletingPolicy}>
              Delete Policy
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

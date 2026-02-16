from collections import deque

class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right

def right_side_view(root):
    if not root:
        return []

    queue = deque([root])
    res = []
    
    while queue:
        level_length = len(queue)
        for i in range(level_length):
            node = queue.popleft()
            if i == level_length - 1:
                res.append(node.val)
            if node.left:
                queue.append(node.left)
            if node.right:
                queue.append(node.right)
    return res

# Test 1
root1 = TreeNode(1, TreeNode(2, None, TreeNode(5)), TreeNode(3, None, TreeNode(4)))
assert right_side_view(root1) == [1, 3, 4]

# Test 2
root2 = TreeNode(1, TreeNode(2, TreeNode(4)), TreeNode(3))
assert right_side_view(root2) == [1, 3, 4]

# Test 3
root3 = TreeNode(1)
assert right_side_view(root3) == [1]

# Test 4
assert right_side_view(None) == []

print("All tests passed!")